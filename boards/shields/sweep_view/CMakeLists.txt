if(CONFIG_ZMK_DISPLAY AND CONFIG_SWEEP_VIEW_STATUS)
  # The animations are drawn as PBM frames and display.json picks one per
  # layer; build_art.py turns them into C here, so only the art is in git.
  set(SWEEP_VIEW_GEN ${CMAKE_CURRENT_BINARY_DIR}/sweep_view_art)
  file(GLOB_RECURSE SWEEP_VIEW_FRAMES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/art/*.pbm)
  add_custom_command(
    OUTPUT ${SWEEP_VIEW_GEN}/art.c ${SWEEP_VIEW_GEN}/art.h
    COMMAND ${PYTHON_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/build_art.py
            ${CMAKE_CURRENT_SOURCE_DIR} ${SWEEP_VIEW_GEN}
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/tools/build_art.py
            ${CMAKE_CURRENT_SOURCE_DIR}/display.json
            ${SWEEP_VIEW_FRAMES}
    COMMENT "Generating nice!view art"
  )

  zephyr_library()
  zephyr_library_include_directories(${CMAKE_SOURCE_DIR}/include ${SWEEP_VIEW_GEN})
  zephyr_library_sources(
    src/custom_status_screen.c
    src/status.c
    ${SWEEP_VIEW_GEN}/art.c
  )
endif()
