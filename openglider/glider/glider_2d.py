from __future__ import division
import copy

import scipy.interpolate
import numpy

from openglider.airfoil.parametric import BezierProfile2D
from openglider.glider import Glider
from openglider.glider.rib_elements import AttachmentPoint
from openglider.vector import mirror2D_x
from openglider.utils.bezier import BezierCurve, SymmetricBezier
from openglider.utils import sign
from openglider.lines import Node, Line, LineSet
from openglider.vector.polyline import PolyLine2D
from openglider.vector.functions import norm, normalize, rotation_2d
from openglider.glider.rib import Rib
from openglider.glider.cell import Cell
from openglider.glider.cell_elements import Panel


class Glider2D(object):
    """
    A parametric (2D) Glider object used for gui input
    """
    def __init__(self, front, back, cell_dist, cell_num, arc,
                 aoa, profiles, lineset,
                 speed, glide):
        self.front = front
        self.back = back
        self.cell_num = cell_num  # updates cell pos
        self.cell_dist = cell_dist
        self.arc = arc
        self.aoa = aoa
        self.profiles = profiles or []
        self.lineset = lineset or LineSet2D([], [])
        self.speed = speed
        self.glide = glide

    @classmethod
    def create_default(cls):
        front = SymmetricBezier()
        back = SymmetricBezier()
        cell_dist = BezierCurve()
        arc = BezierCurve()
        aoa = BezierCurve()

    def __json__(self):
        return {
            "front": self.front,
            "back": self.back,
            "cell_dist": self.cell_dist,
            "cell_num": self.cell_num,
            "arc": self.arc,
            "aoa": self.aoa,
            "profiles": self.profiles,
            "lineset": self.lineset,
            "speed": self.speed,
            "glide": self.glide
        }

    @property
    def v_inf(self):
        angle = numpy.arctan(1/self.glide)
        return numpy.array([-numpy.cos(angle), 0 , numpy.sin(angle)]) * self.speed

    def get_arc_positions(self, num=50):
        # calculating y/z values vor the arc-curve
        x_values = numpy.array(self.cell_dist_interpolation).T[0] #array of scalars
        arc_curve = PolyLine2D([self.arc(i) for i in numpy.linspace(0.5, 1, num)])  # Symmetric-Bezier-> start from 0.5
        arc_curve_length = arc_curve.get_length()

        _positions = [arc_curve.extend(0, x/x_values[-1]*arc_curve_length) for x in x_values]
        positions = PolyLine2D([arc_curve[p] for p in _positions])
        # rescale
        factor = x_values[-1]/positions.get_length()
        positions.scale(factor)
        return positions

    def get_arc_angles(self, arc_curve=None):
        # calculate rib rotations from arc
        arc_curve = arc_curve or self.get_arc_positions()
        arc_curve = [arc_curve[i] for i in range(len(arc_curve))]
        angles = []
        if arc_curve[0][0] == 0:
            angles.append(0)
        else:
            p0 = arc_curve[0]
            p_mirrored = [p0[0]*(-1), p0[1]]
            arc_curve.insert(0, p_mirrored)

        for i in range(len(arc_curve)-1):
            # before
            d = normalize(arc_curve[i+1]-arc_curve[i])
            if i+2 < len(arc_curve):
                # after
                d += normalize(arc_curve[i+2]-arc_curve[i+1])

            angles.append(numpy.arctan2(-d[1], d[0]))

        return angles

    def shape(self, num=30):
        front_int = self.front.interpolate_3d(num=num)
        back_int = self.back.interpolate_3d(num=num)
        dist_line = self.cell_dist_interpolation
        dist = [i[0] for i in dist_line]
        front_line = [front_int(x) for x in dist]
        front = mirror2D_x(front_line)[::-1] + front_line
        back = [back_int(x) for x in dist]
        back = mirror2D_x(back)[::-1] + back
        ribs = zip(front, back)
        return [ribs, front, back]

    def ribs(self, num=30):
        front_int = self.front.interpolate_3d(num=num)
        back_int = self.back.interpolate_3d(num=num)
        dist_line = self.cell_dist_interpolation
        dist = [i[0] for i in dist_line]
        front = [front_int(x) for x in dist]
        back = [back_int(x) for x in dist]
        return zip(front, back)

    def shape_point(self, rib_no, x):
        ribs = self.ribs()
        rib = ribs[rib_no]
        return rib[0] + x * (rib[1] - rib[0])

    def set_span(self, span):
        """
        rescale BezierCurves
        """
        for attr in 'back', 'front', 'cell_dist', 'aoa':
            el = getattr(self, attr)
            factor = span/el.controlpoints[-1][0]
            el.controlpoints = [[p[0]*factor, p[1]] for p in el.controlpoints]

    @property
    def cell_dist_controlpoints(self):
        return self.cell_dist.controlpoints[1:-1]

    @cell_dist_controlpoints.setter
    def cell_dist_controlpoints(self, arr):
        self.cell_dist.controlpoints = [[0, 0]] + arr + [[self.front.controlpoints[-1][0], 1]]

    @property
    def cell_dist_interpolation(self):
        """
        Interpolate Cell-distribution
        """
        interpolation = self.cell_dist.interpolate_3d(num=20, axis=1)
        start = (self.cell_num % 2) / self.cell_num
        return [interpolation(i) for i in numpy.linspace(start, 1, num=self.cell_num // 2 + 1)]

    def depth_integrated(self, num=100):
        """
        Return A(x)
        """
        x_values = numpy.linspace(0, self.front.controlpoints[-1][0], num)
        front_int = self.front.interpolate_3d(num=num)
        back_int = self.back.interpolate_3d(num=num)
        integrated_depth = [0.]
        for x in x_values[1:]:
            integrated_depth.append(integrated_depth[-1] + 1. / (front_int(x)[1] - back_int(x)[1]))
        return zip(x_values, [i / integrated_depth[-1] for i in integrated_depth])

    @property
    def span(self):
        return self.cell_dist_interpolation[-1][0] * 2

    @property
    def attachment_points(self):
        """coordinates of the attachment_points"""
        return [a_p.get_2d(self) for a_p in self.lineset.nodes if isinstance(a_p, up_att_point)]

    @classmethod
    def fit_glider_3d(cls, glider, numpoints=3):
        """
        Create a parametric model from glider
        """
        def mirror_x(polyline):
            mirrored = [[-p[0], p[1]] for p in polyline[1:]]
            return mirrored[::-1] + polyline[glider.has_center_cell:]

        front, back = glider.shape_simple
        arc = [rib.pos[1:] for rib in glider.ribs]
        aoa = [[front[i][0], rib.aoa_relative] for i, rib in enumerate(glider.ribs)]

        front_bezier = SymmetricBezier.fit(mirror_x(front), numpoints=numpoints)
        back_bezier = SymmetricBezier.fit(mirror_x(back), numpoints=numpoints)
        arc_bezier = SymmetricBezier.fit(mirror_x(arc), numpoints=numpoints)
        aoa_bezier = SymmetricBezier.fit(mirror_x(aoa), numpoints=numpoints)

        cell_num = len(glider.cells) * 2 - glider.has_center_cell

        front[0][0] = 0  # for midribs
        start = (2 - glider.has_center_cell) / cell_num
        const_arr = [0.] + numpy.linspace(start, 1, len(front) - 1).tolist()
        rib_pos = [0.] + [p[0] for p in front[1:]]
        rib_pos_int = scipy.interpolate.interp1d(rib_pos, [rib_pos, const_arr])
        rib_distribution = [rib_pos_int(i) for i in numpy.linspace(0, rib_pos[-1], 30)]
        rib_distribution = BezierCurve.fit(rib_distribution, numpoints=numpoints+3)

        profiles = [rib.profile_2d for rib in glider.ribs]
        profile_dist = BezierCurve.fit([[i, i] for i in range(len(profiles))],
                                       numpoints=numpoints)

        # TODO: lineset

        return cls(front=front_bezier,
                   back=back_bezier,
                   cell_dist=rib_distribution,
                   cell_num=cell_num,
                   arc=arc_bezier,
                   aoa=aoa_bezier,
                   profiles=profiles,
                   glide=glider.glide,
                   speed=10,
                   lineset=LineSet2D([],[]))

    def get_glider_3d(self, glider=None, num=50):
        """returns a new glider from parametric values"""
        glider = glider or Glider()
        ribs = []
        cells = []
        print("Jojo")

        # TODO airfoil, ballooning-------
        airfoil = self.profiles[0]
        aoa_int = numpy.deg2rad(13.)
        #--------------------------------------

        glide = self.glide
        x_values = [rib_no[0] for rib_no in self.cell_dist_interpolation]
        front_int = self.front.interpolate_3d(num=num)
        back_int = self.back.interpolate_3d(num=num)
        arc_pos = list(self.get_arc_positions(num=num))
        arc_angles = self.get_arc_angles()
        aoa_cp = self.aoa.controlpoints
        aoa_x_factor = x_values[-1] / aoa_cp[-1][0]
        self.aoa.controlpoints = [[p[0] * aoa_x_factor, p[1]] for p in aoa_cp]
        aoa_int = self.aoa.interpolate_3d(num=num)

        if x_values[0] != 0.:
            # adding the mid cell
            x_values = [-x_values[0]] + x_values
            arc_pos = [[-arc_pos[0][0], arc_pos[0][1]]] + arc_pos
            arc_angles = [-arc_angles[0]] + arc_angles

        for rib_no, pos in enumerate(x_values):
            front = front_int(pos)
            back = back_int(pos)
            arc = arc_pos[rib_no]
            ribs.append(Rib(
                profile_2d=airfoil.copy(),
                startpoint=numpy.array([-front[1], arc[0], arc[1]]),
                chord=norm(front - back),
                arcang=arc_angles[rib_no],
                glide=glide,
                aoa_absolute=aoa_int(pos)[1]
                ))
            ribs[-1].aoa_relative = aoa_int(pos)[1]
        for rib_no, rib in enumerate(ribs[1:]):
            cell = Cell(ribs[rib_no], rib, [])
            cell.panels = [Panel([-1, -1, 3, 0.012], [1, 1, 3, 0.012], rib_no)]
            cells.append(cell)
            glider.cells = cells
        glider.close_rib()

        glider.lineset = self.lineset.return_lineset(glider)
        glider.lineset.calc_geo()
        glider.lineset.calc_sag()

        return glider


        # set up the lines here
        # the data for the attachment_points is only stored in glider_2d
        # make a new lineset from the 2d lines 
        # and append it to the glider


#######################################line objects######################################
class lower_attachment_point(object):
    """lower attachment point"""
    def __init__(self, pos, pos3D, nr=None):
        self.pos = pos
        self.pos3D = pos3D
        self.nr = nr

    def __json__(self):
        return{
            "pos": self.pos,
            "pos3D": self.pos3D,
            "nr": self.nr}

    @classmethod
    def __from_json__(cls, pos, pos3D, nr):
        p = cls(pos, pos3D)
        p.nr = nr
        return p

    def get_node(self, glider):
        return Node(node_type=0, position_vector=numpy.array(self.pos3D))


class up_att_point(object):
    """stores the 2d data of an attachment point"""
    def __init__(self, rib_no, position, force=1., nr=None):
        self.rib_no = rib_no
        self.position = position  # value from 0...100
        self.force = force
        self.nr = nr

    def __json__(self):
        return {'rib_no': self.rib_no,
                'position': self.position,
                'force': self.force,
                'nr': self.nr}

    def get_2d(self, glider_2d):
        _, front, back = glider_2d.shape()
        xpos = numpy.unique([i[0] for i in front if i[0] >= 0.])
        pos = self.position / 100.
        if self.rib_no < len(xpos):
            x = xpos[self.rib_no]
            j = self.rib_no + len(front) - len(xpos)
            chord = back[j][1] - front[j][1]
            y = front[j][1] + pos * chord
            return x, y

    def get_node(self, glider):
        node = AttachmentPoint(glider.ribs[self.rib_no], None,
                               self.position/100, [0, 0, self.force])
        node.get_position()
        return node


class batch_point(object):
    def __init__(self, pos_2d, nr=None):
        self.pos_2d = pos_2d  # pos => 2d coordinates
        self.nr = nr

    def __json__(self):
        return{
            "pos_2d": self.pos_2d,
            "nr": self.nr
            }

    def get_node(self, glider):
        return Node(node_type=1)


class LineSet2D(object):
    def __init__(self, line_list, node_list):
        self.lines = line_list
        self.nodes = node_list

    def __json__(self):
        lines = [copy.copy(line) for line in self.lines]
        nodes = self.nodes
        print(self.nodes)
        for line in lines:
            line.upper_point = nodes.index(line.upper_point)
            line.lower_point = nodes.index(line.lower_point)
        return {"lines": lines,
                "nodes": nodes
                }

    @classmethod
    def __from_json__(cls, lines, nodes):
        lineset = cls(lines, nodes)
        nodes = lineset.nodes
        for line in lineset.lines:
            if isinstance(line.upper_point, int):
                line.upper_point = nodes[line.upper_point]
            if isinstance(line.lower_point, int):
                line.lower_point = nodes[line.lower_point]
        return lineset

    def return_lineset(self, glider):
        lines = []
        # first get the lowest points (lw-att)
        lowest = [node for node in self.nodes if isinstance(node, lower_attachment_point)]
        # now get the connected lines
        # get the other point (change the nodes if necesarry)
        for node in lowest:
            self.sort_lines(node)
        self.delete_not_connected(glider)
        for node in self.nodes:
            node.temp_node = node.get_node(glider)  # store the nodes to remember them with the lines
        # set up the lines!
        for line_no, line in enumerate(self.lines):
            lower = line.lower_point.temp_node
            upper = line.upper_point.temp_node
            if lower and upper:
                line = Line(number=line_no, lower_node=lower, upper_node=upper,
                            vinf=glider.v_inf, target_length=line.target_length)
                lines.append(line)

        return LineSet(lines, glider.v_inf)

    def sort_lines(self, lower_att):
        """
        Recursive sorting of lines (check direction)
        """
        for line in self.lines:
            if not line.is_sorted:
                if lower_att == line.upper_point:
                    line.lower_point, line.upper_point = line.upper_point, line.lower_point
                if lower_att == line.lower_point:
                    line.is_sorted = True
                    self.sort_lines(line.upper_point)

    def delete_not_connected(self, glider):
        temp = []
        temp_new = []
        for line in self.lines:
            if isinstance(line.upper_point, up_att_point):
                if line.upper_point.rib_no >= len(glider.ribs):
                    temp.append(line)
                    self.nodes.remove(line.upper_point)

        while temp:
            for line in temp:
                conn_up_lines = [j for j in self.lines if (j.lower_point == line.lower_point and j != line)]
                conn_lo_lines = [j for j in self.lines if (j.upper_point == line.lower_point and j != line)]
                if len(conn_up_lines) == 0:
                    self.nodes.remove(line.lower_point)
                    self.lines.remove(line)
                    temp_new += conn_lo_lines
                temp.remove(line)
            temp = temp_new


class Line2D(object):
    def __init__(self, lower_node, upper_node, target_length=None):
        self.lower_node = lower_node
        self.upper_node = upper_node
        self.target_length = target_length
        self.is_sorted = False

    def __json__(self):
        return{
            "lower_node": self.lower_node,
            "upper_node": self.upper_node,
            "target_length": self.target_length,
        }



if __name__ == "__main__":
    a = BezierProfile2D.compute_naca()
    import openglider.graphics as g
    g.Graphics3D([
        g.Line(a.upper_spline.get_sequence()),
        g.Line(a.upper_spline.controlpoints),
        g.Line(a.lower_spline.get_sequence()),
        g.Line(a.lower_spline.controlpoints),
        g.Point(a.data)
        ])