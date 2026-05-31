#include <pybind11/pybind11.h>
#include "guimma_engine.h"

namespace py = pybind11;

PYBIND11_MODULE(guimma_geometry_cpp, m) {

    py::class_<guimma::Point>(m, "Point")
        .def(py::init<>())
        .def_readwrite("x", &guimma::Point::x)
        .def_readwrite("y", &guimma::Point::y);

    m.def("distance", [](double ax, double ay, double bx, double by) {
        return guimma::distance({ax, ay}, {bx, by});
    });
}
