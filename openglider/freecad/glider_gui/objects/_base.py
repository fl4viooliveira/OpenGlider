from pivy import coin
import FreeCADGui as gui
from openglider.utils.bezier import BezierCurve


def None_func():
    pass

#-------------------------BEGIN-BASE-Object-----------------------#
class ControlPoint(coin.SoSeparator):
    def __init__(self, x=0, y=0, z=0):
        super(ControlPoint, self).__init__()
        self.marker = coin.SoMarkerSet()
        self.marker.markerIndex = coin.SoMarkerSet.CROSS_5_5
        self.mat = coin.SoMaterial()
        self.mat.diffuseColor.setValue(0., 0., 0.)
        self.coordinate = coin.SoCoordinate3()
        self.set_pos([x, y, z])
        self.switch = coin.SoSwitch()
        self.addChild(self.coordinate)
        self.addChild(self.switch)
        self.addChild(self.mat)
        self.addChild(self.marker)

        self.mouse_over = False

    def set_pos(self, new_pos):
        self.x, self.y, self.z = self.constraint(new_pos)
        self.coordinate.point.setValue(self.x, self.y, self.z)

    def set_edit_mode(self):
        self.marker.markerIndex = coin.SoMarkerSet.CIRCLE_FILLED_7_7

    def unset_edit_mode(self):
        self.marker.markerIndex = coin.SoMarkerSet.CROSS_5_5

    def set_mouse_over(self):
        self.mouse_over = True
        self.mat.diffuseColor.setValue(1, 1, 0)

    def unset_mouse_over(self):
        self.mouse_over = False
        self.mat.diffuseColor.setValue(0, 0, 0)

    def constraint(self, pos):
        "overwrite for special behavior"
        return [pos[0], pos[1], 0.]


class ControlPointContainer(coin.SoSeparator):
    def __init__(self, points=None):
        super(ControlPointContainer, self).__init__()
        self.control_points = [ControlPoint(*point) for point in points]
        for cp in self.control_points:
            self.addChild(cp)

        self.view = None
        self.highlite_main = None
        self.drag = None
        self.drag_check = False
        self.current_point = None
        self.trigger_func = None
        self.is_edit = False

    @property
    def control_point_list(self):
        return [[i.x, i.y, i.z] for i in self.control_points]

    def set_edit_mode(self, view, triggerfunc=None_func):
        print(self.is_edit)
        if not self.is_edit:
            self.is_edit = True
            self.view = view
            self.trigger_func = triggerfunc
            for pt in self.control_points:
                pt.set_edit_mode()
            self.highlite_main = self.view.addEventCallbackPivy(coin.SoLocation2Event.getClassTypeId(), self.highlight_cb)
            self.drag_main = self.view.addEventCallbackPivy(coin.SoMouseButtonEvent.getClassTypeId(), self.drag_main_cb)
            self.exit = self.view.addEventCallbackPivy(coin.SoKeyboardEvent.getClassTypeId(), self.exit_cb)
        else:
            self.unset_edit_mode()


    def unset_edit_mode(self):
        if self.is_edit:
            self.is_edit = False
            self.view.removeEventCallbackPivy(coin.SoLocation2Event.getClassTypeId(), self.highlite_main)
            self.view.removeEventCallbackPivy(coin.SoMouseButtonEvent.getClassTypeId(), self.drag_main)
            self.view.removeEventCallbackPivy(coin.SoKeyboardEvent.getClassTypeId(), self.exit)
            for pt in self.control_points:
                pt.unset_edit_mode()
            self.view = None

    def exit_cb(self, event_callback):
        event = event_callback.getEvent()
        print(event.getKey())
        if event.getKey() == 65307:
            self.unset_edit_mode()


    def highlight_cb(self, event_callback):
        event = event_callback.getEvent()
        pos = event.getPosition()
        #-------------HIGHLIGHT----------------#
        if not self.drag:
            if type(event) == coin.SoLocation2Event:
                self.current_point = None
                for point in self.control_points:
                    s = self.view.getPointOnScreen(point.x, point.y, point.z)
                    if (abs(s[0] - pos[0]) ** 2 + abs(s[1] - pos[1]) ** 2) < (15 ** 2):
                        self.current_point = point
                        if not point.mouse_over:
                            point.set_mouse_over()
                    else:
                        if point.mouse_over:
                            point.unset_mouse_over()

    #---------INITDRAG---------------------#
    def drag_main_cb(self, event_callback):
        event = event_callback.getEvent()
        if self.current_point is not None and not self.drag_check:
            self.drag_check = True
            self.drag = self.view.addEventCallbackPivy(coin.SoLocation2Event.getClassTypeId(), self.drag_cb)
        elif self.drag is not None and self.drag_check:
            self.drag_check = False
            self.view.removeEventCallbackPivy(coin.SoLocation2Event.getClassTypeId(), self.drag)
            self.drag = None

    def drag_cb(self, event_callback):
        event = event_callback.getEvent()
        pos = event.getPosition()
        if type(event) == coin.SoLocation2Event:
            self.current_point.set_pos(self.view.getPoint(pos[0], pos[1]))
            self.trigger_func()

    def add_point(self):
        pass

    def sort(self):
        pass

    def remove_point(self):
        pass
