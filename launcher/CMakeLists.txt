cmake_minimum_required(VERSION 3.24)
project(OrlaLauncher VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.11.2 REQUIRED COMPONENTS Core Gui Widgets Qml Quick DBus)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_package(KF6Runner 6.30 REQUIRED)
find_package(KF6Config 6.30 REQUIRED)
find_package(KF6GlobalAccel 6.30 REQUIRED)
find_package(KF6WindowSystem 6.30 REQUIRED)

set(ORLA_AI_HELPER_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../scripts/ai.py" CACHE FILEPATH
    "Absolute path to the bounded Orla AI provider helper")
if(NOT IS_ABSOLUTE "${ORLA_AI_HELPER_PATH}")
    message(FATAL_ERROR "ORLA_AI_HELPER_PATH must be absolute")
endif()
set(ORLA_AI_TEXT_HELPER_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../scripts/ai_text_ollama.py" CACHE FILEPATH
    "Absolute path to the operational Orla local text helper")
if(NOT IS_ABSOLUTE "${ORLA_AI_TEXT_HELPER_PATH}")
    message(FATAL_ERROR "ORLA_AI_TEXT_HELPER_PATH must be absolute")
endif()
set(ORLA_STEAM_HELPER_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../scripts/steam.py" CACHE FILEPATH
    "Absolute path to the bounded Orla Steam metadata helper")
if(NOT IS_ABSOLUTE "${ORLA_STEAM_HELPER_PATH}")
    message(FATAL_ERROR "ORLA_STEAM_HELPER_PATH must be absolute")
endif()

add_library(orla-launcher-core STATIC LauncherController.cpp LauncherController.h
    AiProviderController.cpp AiProviderController.h
    AiTextController.cpp AiTextController.h
    SteamProviderController.cpp SteamProviderController.h)
target_include_directories(orla-launcher-core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(orla-launcher-core PUBLIC Qt6::Core Qt6::Gui KF6::Runner KF6::ConfigCore)

add_executable(orla-launcher main.cpp WindowSession.cpp WindowSession.h)
target_compile_definitions(orla-launcher PRIVATE
    ORLA_AI_PYTHON_PATH="${Python3_EXECUTABLE}"
    ORLA_AI_HELPER_PATH="${ORLA_AI_HELPER_PATH}"
    ORLA_AI_TEXT_HELPER_PATH="${ORLA_AI_TEXT_HELPER_PATH}"
    ORLA_STEAM_PYTHON_PATH="${Python3_EXECUTABLE}"
    ORLA_STEAM_HELPER_PATH="${ORLA_STEAM_HELPER_PATH}")
qt_add_resources(orla-launcher ui PREFIX "/orla" FILES Launcher.qml AiSettings.qml SteamSettings.qml Style.js)
target_link_libraries(orla-launcher PRIVATE orla-launcher-core Qt6::Widgets Qt6::Qml Qt6::Quick Qt6::DBus
    KF6::GlobalAccel KF6::WindowSystem)

include(CTest)
if(BUILD_TESTING)
    find_package(Qt6 6.11.2 REQUIRED COMPONENTS Test DBus Network)
    find_program(ORLA_DBUS_DAEMON dbus-daemon REQUIRED)
    find_program(ORLA_GDBUS gdbus REQUIRED)
    add_executable(orla-launcher-tests tests/LauncherTests.cpp)
    target_compile_definitions(orla-launcher-tests PRIVATE
        ORLA_TEST_PYTHON_EXECUTABLE="${Python3_EXECUTABLE}")
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
    add_executable(orla-launcher-ui-tests tests/UiTests.cpp WindowSession.cpp WindowSession.h)
    target_compile_definitions(orla-launcher-ui-tests PRIVATE
        ORLA_TEST_PYTHON_EXECUTABLE="${Python3_EXECUTABLE}")
    qt_add_resources(orla-launcher-ui-tests ui PREFIX "/orla" FILES Launcher.qml AiSettings.qml SteamSettings.qml Style.js)
    target_link_libraries(orla-launcher-ui-tests PRIVATE orla-launcher-core Qt6::Widgets Qt6::Quick Qt6::Qml Qt6::Test Qt6::DBus
        KF6::GlobalAccel KF6::WindowSystem)
    add_test(NAME launcher-ui COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_isolated.py
        --private-path
        $<TARGET_FILE:orla-launcher-ui-tests>)
    set_tests_properties(launcher-ui PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software" TIMEOUT 30)
    add_executable(orla-launcher-managed-dispatch-harness tests/ManagedDispatchHarness.cpp WindowSession.cpp WindowSession.h)
    get_target_property(ORLA_MAIN_DEFINITIONS orla-launcher COMPILE_DEFINITIONS)
    target_compile_definitions(orla-launcher-managed-dispatch-harness PRIVATE ${ORLA_MAIN_DEFINITIONS})
    qt_add_resources(orla-launcher-managed-dispatch-harness ui PREFIX "/orla" FILES Launcher.qml AiSettings.qml SteamSettings.qml Style.js)
    target_link_libraries(orla-launcher-managed-dispatch-harness PRIVATE orla-launcher-core Qt6::Widgets Qt6::Quick Qt6::Qml Qt6::Test Qt6::DBus
        KF6::GlobalAccel KF6::WindowSystem)
    add_executable(orla-launcher-shortcut-tests tests/ShortcutTests.cpp WindowSession.cpp WindowSession.h)
    target_compile_definitions(orla-launcher-shortcut-tests PRIVATE ORLA_TEST_LAUNCHER="$<TARGET_FILE:orla-launcher>"
        ORLA_TEST_DISPATCH_HARNESS="$<TARGET_FILE:orla-launcher-managed-dispatch-harness>")
    target_link_libraries(orla-launcher-shortcut-tests PRIVATE orla-launcher-core Qt6::Widgets Qt6::Quick Qt6::Test Qt6::DBus
        KF6::GlobalAccel KF6::WindowSystem)
    add_test(NAME launcher-shortcuts COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_isolated.py
        --private-path --fixture $<TARGET_FILE:orla-launcher-test-fixture> $<TARGET_FILE:orla-launcher-shortcut-tests>)
    set_tests_properties(launcher-shortcuts PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software" TIMEOUT 30)
    add_executable(orla-ai-provider-tests tests/AiProviderTests.cpp)
    target_compile_definitions(orla-ai-provider-tests PRIVATE
        ORLA_TEST_PYTHON_EXECUTABLE="${Python3_EXECUTABLE}")
    target_link_libraries(orla-ai-provider-tests PRIVATE orla-launcher-core Qt6::Test)
    add_test(NAME launcher-ai-provider COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_isolated.py
        --private-path
        $<TARGET_FILE:orla-ai-provider-tests>)
    set_tests_properties(launcher-ai-provider PROPERTIES TIMEOUT 40)
    add_executable(orla-steam-provider-tests tests/SteamProviderTests.cpp)
    target_compile_definitions(orla-steam-provider-tests PRIVATE
        ORLA_TEST_PYTHON_EXECUTABLE="${Python3_EXECUTABLE}"
        ORLA_TEST_STEAM_HELPER="${ORLA_STEAM_HELPER_PATH}")
    target_link_libraries(orla-steam-provider-tests PRIVATE orla-launcher-core Qt6::Test Qt6::Qml Qt6::Quick)
    add_test(NAME launcher-steam-provider COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_isolated.py
        --private-path
        $<TARGET_FILE:orla-steam-provider-tests>)
    set_tests_properties(launcher-steam-provider PROPERTIES TIMEOUT 40)
    add_executable(orla-ai-text-tests tests/AiTextControllerTests.cpp)
    target_compile_definitions(orla-ai-text-tests PRIVATE
        ORLA_TEST_PYTHON_EXECUTABLE="${Python3_EXECUTABLE}"
        ORLA_TEST_AI_TEXT_HELPER="${ORLA_AI_TEXT_HELPER_PATH}")
    target_link_libraries(orla-ai-text-tests PRIVATE orla-launcher-core Qt6::Test Qt6::Network)
    add_test(NAME launcher-ai-text COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_isolated.py
        --private-path
        $<TARGET_FILE:orla-ai-text-tests>)
    set_tests_properties(launcher-ai-text PROPERTIES TIMEOUT 40)
    set_tests_properties(launcher-behavior launcher-ui launcher-shortcuts launcher-owned-app launcher-ai-provider launcher-ai-text launcher-steam-provider
        PROPERTIES ENVIRONMENT_MODIFICATION "LD_LIBRARY_PATH=unset:")
endif()
