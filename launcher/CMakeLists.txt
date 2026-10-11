cmake_minimum_required(VERSION 3.24)
project(OrlaLauncher VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.11.2 REQUIRED COMPONENTS Core Gui Widgets Qml Quick)
find_package(KF6Runner 6.30 REQUIRED)
find_package(KF6Config 6.30 REQUIRED)
find_package(KF6GlobalAccel 6.30 REQUIRED)
find_package(KF6WindowSystem 6.30 REQUIRED)

add_library(orla-launcher-core STATIC LauncherController.cpp LauncherController.h)
target_include_directories(orla-launcher-core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(orla-launcher-core PUBLIC Qt6::Core KF6::Runner KF6::ConfigCore)

add_executable(orla-launcher main.cpp WindowSession.cpp WindowSession.h)
qt_add_resources(orla-launcher ui PREFIX "/orla" FILES Launcher.qml)
target_link_libraries(orla-launcher PRIVATE orla-launcher-core Qt6::Widgets Qt6::Qml Qt6::Quick
    KF6::GlobalAccel KF6::WindowSystem)

include(CTest)
if(BUILD_TESTING)
    find_package(Qt6 6.11.2 REQUIRED COMPONENTS Test DBus)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    find_program(ORLA_DBUS_DAEMON dbus-daemon REQUIRED)
    find_program(ORLA_GDBUS gdbus REQUIRED)
    add_executable(orla-launcher-tests tests/LauncherTests.cpp)
    target_link_libraries(orla-launcher-tests PRIVATE orla-launcher-core Qt6::Widgets Qt6::Test Qt6::DBus)
    add_test(NAME launcher-behavior COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_isolated.py
        $<TARGET_FILE:orla-launcher-tests>)
    set_tests_properties(launcher-behavior PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen" TIMEOUT 30)
    add_executable(orla-launcher-test-fixture tests/Fixture.cpp)
    target_link_libraries(orla-launcher-test-fixture PRIVATE Qt6::Core)
    add_test(NAME launcher-owned-app COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_isolated.py
        --fixture $<TARGET_FILE:orla-launcher-test-fixture> $<TARGET_FILE:orla-launcher-tests>
        appResultsOnlyRunOwnedFixtureAfterExplicitSelection)
    set_tests_properties(launcher-owned-app PROPERTIES TIMEOUT 30)
    add_executable(orla-launcher-ui-tests tests/UiTests.cpp)
    qt_add_resources(orla-launcher-ui-tests ui PREFIX "/orla" FILES Launcher.qml)
    target_link_libraries(orla-launcher-ui-tests PRIVATE orla-launcher-core Qt6::Widgets Qt6::Quick Qt6::Qml Qt6::Test Qt6::DBus)
    add_test(NAME launcher-ui COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_isolated.py
        $<TARGET_FILE:orla-launcher-ui-tests>)
    set_tests_properties(launcher-ui PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software" TIMEOUT 30)
    set_tests_properties(launcher-behavior launcher-ui launcher-owned-app PROPERTIES ENVIRONMENT_MODIFICATION "LD_LIBRARY_PATH=unset:")
endif()
