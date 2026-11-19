#include <lvgl.h>

#include "status.h"

lv_obj_t *zmk_display_status_screen(void) {
    lv_obj_t *screen = lv_obj_create(NULL);
    sweep_view_status_init(screen);
    return screen;
}
