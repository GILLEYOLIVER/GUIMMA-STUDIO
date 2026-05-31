#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "guimma_engine.h"
#include "snap_engine.h"
#include "spatial_index.h"

namespace py = pybind11;

PYBIND11_MODULE(guimma_geometry_cpp, m) {
    m.doc() = "Motor geometrico C++ do GUIMMA STUDIO";

    py::class_<guimma::Point>(m, "Point")
        .def(py::init<>())
        .def(py::init<double, double>())
        .def_readwrite("x", &guimma::Point::x)
        .def_readwrite("y", &guimma::Point::y);

    py::enum_<guimma::SnapKind>(m, "SnapKind")
        .value("NONE", guimma::SnapKind::None)
        .value("NODE", guimma::SnapKind::Node)
        .value("CONTROL", guimma::SnapKind::Control)
        .value("MAIN_CONTROL", guimma::SnapKind::MainControl)
        .value("HELPER_CONTROL", guimma::SnapKind::HelperControl)
        .value("BORDER", guimma::SnapKind::Border)
        .value("MIDPOINT", guimma::SnapKind::Midpoint)
        .value("CENTER", guimma::SnapKind::Center)
        .value("INTERSECTION", guimma::SnapKind::Intersection)
        .value("GRID", guimma::SnapKind::Grid)
        .value("COORD", guimma::SnapKind::Coord)
        .value("GRAINLINE", guimma::SnapKind::Grainline)
        .value("LABEL", guimma::SnapKind::Label);

    py::class_<guimma::SnapPoint>(m, "SnapPoint")
        .def(py::init<>())
        .def_readwrite("point", &guimma::SnapPoint::point)
        .def_readwrite("kind", &guimma::SnapPoint::kind)
        .def_readwrite("element_index", &guimma::SnapPoint::element_index)
        .def_readwrite("distance", &guimma::SnapPoint::distance)
        .def_readwrite("priority", &guimma::SnapPoint::priority)
        .def_property_readonly("kind_text", [](const guimma::SnapPoint& p) {
            return guimma::snap_kind_to_string(p.kind);
        });

    py::class_<guimma::PolylineElement>(m, "PolylineElement")
        .def(py::init<>())
        .def_readwrite("element_index", &guimma::PolylineElement::element_index)
        .def_readwrite("points", &guimma::PolylineElement::points)
        .def_readwrite("main_controls", &guimma::PolylineElement::main_controls)
        .def_readwrite("helper_controls", &guimma::PolylineElement::helper_controls)
        .def_readwrite("official_controls", &guimma::PolylineElement::official_controls)
        .def_readwrite("participates", &guimma::PolylineElement::participates)
        .def_readwrite("element_priority", &guimma::PolylineElement::element_priority);

    py::class_<guimma::SnapEngine>(m, "SnapEngine")
        .def(py::init<>())
        .def("clear", &guimma::SnapEngine::clear)
        .def("set_tolerance_px", &guimma::SnapEngine::set_tolerance_px)
        .def("set_grid", &guimma::SnapEngine::set_grid)
        .def("add_polyline", &guimma::SnapEngine::add_polyline)
        .def("candidates", &guimma::SnapEngine::candidates, py::arg("cursor"), py::arg("zoom"), py::arg("tolerance_px") = -1.0)
        .def("nearest", &guimma::SnapEngine::nearest, py::arg("cursor"), py::arg("zoom"), py::arg("tolerance_px") = -1.0)
        .def("element_count", &guimma::SnapEngine::element_count)
        .def("segment_count", &guimma::SnapEngine::segment_count);

    m.def("distance", [](double ax, double ay, double bx, double by) {
        return guimma::distance({ax, ay}, {bx, by});
    });

    m.def("project_on_segment", [](double px, double py, double ax, double ay, double bx, double by) {
        const auto p = guimma::project_on_segment({px, py}, {ax, ay}, {bx, by});
        return py::make_tuple(p.x, p.y);
    });

    m.def("snap_kind_to_string", &guimma::snap_kind_to_string);
}
