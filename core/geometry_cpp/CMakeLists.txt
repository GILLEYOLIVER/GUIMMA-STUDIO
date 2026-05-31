cmake_minimum_required(VERSION 3.20)

project(guimma_geometry_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(guimma_geometry_cpp
    bindings.cpp
    guimma_engine.cpp
    spatial_index.cpp
    snap_engine.cpp
    curve_engine.cpp
    intersection_engine.cpp
    contour_engine.cpp
)

target_include_directories(guimma_geometry_cpp PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

if(APPLE)
    execute_process(
        COMMAND xcrun --sdk macosx --show-sdk-path
        OUTPUT_VARIABLE GUIMMA_MACOS_SDK
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(EXISTS "${GUIMMA_MACOS_SDK}/usr/include/c++/v1")
        target_include_directories(guimma_geometry_cpp SYSTEM PRIVATE "${GUIMMA_MACOS_SDK}/usr/include/c++/v1")
    endif()
endif()

target_compile_definitions(guimma_geometry_cpp PRIVATE VERSION_INFO="0.1.0")

if(MSVC)
    target_compile_options(guimma_geometry_cpp PRIVATE /O2 /permissive- /EHsc)
else()
    target_compile_options(guimma_geometry_cpp PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()
