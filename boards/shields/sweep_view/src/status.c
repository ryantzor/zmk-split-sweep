/*
 * The Sweep's nice!view screen, read standing on end (68 wide, 160 tall):
 *
 *   ┌────────┐
 *   │  art   │  68×68 emblem for the active layer, drawing itself
 *   ├────────┤
 *   │  NAV   │  layer name
 *   │ ▭ 84%  │  battery
 *   │ ᛒ 2    │  USB, or the Bluetooth profile and whether it's connected
 *   ├────────┤
 *   │ ●○○○○  │  Bluetooth profiles
 *   └────────┘
 *
 * The status canvases are drawn upright and turned to match the panel, the
 * same way ZMK's own nice!view screen does (canvas helpers follow its
 * widgets/util.c, MIT, The ZMK Contributors). The art comes pre-turned.
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#include <lvgl.h>
#include <zmk/activity.h>
#include <zmk/battery.h>
#include <zmk/ble.h>
#include <zmk/display.h>
#include <zmk/endpoints.h>
#include <zmk/event_manager.h>
#include <zmk/events/activity_state_changed.h>
#include <zmk/events/battery_state_changed.h>
#include <zmk/events/ble_active_profile_changed.h>
#include <zmk/events/endpoint_changed.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/events/usb_conn_state_changed.h>
#include <zmk/keymap.h>
#include <zmk/usb.h>

#include "art.h"
#include "status.h"

#define CANVAS_SIZE 68
#define CANVAS_FORMAT LV_COLOR_FORMAT_L8 /* the smallest format lv_draw_sw_rotate takes */
#define CANVAS_BUF_SIZE                                                                            \
    LV_CANVAS_BUF_SIZE(CANVAS_SIZE, CANVAS_SIZE, LV_COLOR_FORMAT_GET_BPP(CANVAS_FORMAT),           \
                       LV_DRAW_BUF_STRIDE_ALIGN)
#define PROFILE_COUNT 5

#define BACKGROUND (SWEEP_VIEW_INVERT ? lv_color_black() : lv_color_white())
#define FOREGROUND (SWEEP_VIEW_INVERT ? lv_color_white() : lv_color_black())

struct status {
    uint8_t battery;
    bool charging;
    struct zmk_endpoint_instance endpoint;
    int profile;
    bool profile_connected;
    bool profile_bonded;
    bool bonded[PROFILE_COUNT];
    uint8_t layer;
    const char *layer_name;
};

static struct status state;
static lv_obj_t *art_image;
static lv_obj_t *info_canvas;
static lv_obj_t *profile_canvas;
static uint8_t info_buf[CANVAS_BUF_SIZE];
static uint8_t profile_buf[CANVAS_BUF_SIZE];

/* Drawing */

static void rotate(lv_obj_t *canvas) {
    static uint8_t copy[CANVAS_BUF_SIZE];
    uint8_t *buf = lv_canvas_get_draw_buf(canvas)->data;
    memcpy(copy, buf, sizeof(copy));
    const uint32_t stride = lv_draw_buf_width_to_stride(CANVAS_SIZE, CANVAS_FORMAT);
    lv_draw_sw_rotate(copy, buf, CANVAS_SIZE, CANVAS_SIZE, stride, stride,
                      SWEEP_VIEW_FLIP ? LV_DISPLAY_ROTATION_90 : LV_DISPLAY_ROTATION_270,
                      CANVAS_FORMAT);
}

static void draw_rect(lv_obj_t *canvas, int x, int y, int w, int h, lv_color_t color) {
    lv_draw_rect_dsc_t dsc;
    lv_draw_rect_dsc_init(&dsc);
    dsc.bg_color = color;
    lv_layer_t layer;
    lv_canvas_init_layer(canvas, &layer);
    lv_area_t area = {x, y, x + w - 1, y + h - 1};
    lv_draw_rect(&layer, &dsc, &area);
    lv_canvas_finish_layer(canvas, &layer);
}

static void draw_circle(lv_obj_t *canvas, int x, int y, int r, int width, lv_color_t color) {
    lv_draw_arc_dsc_t dsc;
    lv_draw_arc_dsc_init(&dsc);
    dsc.color = color;
    dsc.width = width;
    dsc.center.x = x;
    dsc.center.y = y;
    dsc.radius = r;
    dsc.start_angle = 0;
    dsc.end_angle = 360;
    lv_layer_t layer;
    lv_canvas_init_layer(canvas, &layer);
    lv_draw_arc(&layer, &dsc);
    lv_canvas_finish_layer(canvas, &layer);
}

static void draw_text(lv_obj_t *canvas, int x, int y, int w, const lv_font_t *font,
                      lv_text_align_t align, const char *text) {
    lv_draw_label_dsc_t dsc;
    lv_draw_label_dsc_init(&dsc);
    dsc.color = FOREGROUND;
    dsc.font = font;
    dsc.align = align;
    dsc.text = text;
    lv_layer_t layer;
    lv_canvas_init_layer(canvas, &layer);
    lv_area_t area = {x, y, x + w - 1, y + CANVAS_SIZE};
    lv_draw_label(&layer, &dsc, &area);
    lv_canvas_finish_layer(canvas, &layer);
}

static void draw_info(void) {
    lv_obj_t *c = info_canvas;
    lv_canvas_fill_bg(c, BACKGROUND, LV_OPA_COVER);

    char name[16];
    if (state.layer < sweep_view_layer_count && sweep_view_layer_names[state.layer][0]) {
        snprintf(name, sizeof(name), "%s", sweep_view_layer_names[state.layer]);
    } else if (state.layer_name && state.layer_name[0]) {
        snprintf(name, sizeof(name), "%s", state.layer_name);
    } else {
        snprintf(name, sizeof(name), "LAYER %d", state.layer);
    }
    draw_text(c, 0, 3, CANVAS_SIZE, &lv_font_montserrat_16, LV_TEXT_ALIGN_CENTER, name);
    draw_rect(c, 6, 26, CANVAS_SIZE - 12, 1, FOREGROUND);

    /* Battery: an outline filled to the charge, with the percentage. */
    draw_rect(c, 4, 34, 24, 12, FOREGROUND);
    draw_rect(c, 5, 35, 22, 10, BACKGROUND);
    draw_rect(c, 6, 36, (state.battery * 20 + 50) / 100, 8, FOREGROUND);
    draw_rect(c, 28, 37, 2, 6, FOREGROUND);
    char battery[8];
    snprintf(battery, sizeof(battery), "%s%d%%", state.charging ? "+" : "", state.battery);
    draw_text(c, 32, 33, CANVAS_SIZE - 32, &lv_font_montserrat_12, LV_TEXT_ALIGN_LEFT, battery);

    char output[16] = {};
    if (state.endpoint.transport == ZMK_TRANSPORT_USB) {
        snprintf(output, sizeof(output), LV_SYMBOL_USB " USB");
    } else {
        const char *mark = !state.profile_bonded       ? LV_SYMBOL_SETTINGS
                           : state.profile_connected ? LV_SYMBOL_BLUETOOTH
                                                     : LV_SYMBOL_CLOSE;
        snprintf(output, sizeof(output), "%s %d", mark, state.profile + 1);
    }
    draw_text(c, 4, 50, CANVAS_SIZE - 4, &lv_font_montserrat_12, LV_TEXT_ALIGN_LEFT, output);

    rotate(c);
}

/* Only the top 24 rows of this canvas are on screen. */
static void draw_profiles(void) {
    lv_obj_t *c = profile_canvas;
    lv_canvas_fill_bg(c, BACKGROUND, LV_OPA_COVER);
    for (int i = 0; i < PROFILE_COUNT; i++) {
        const int x = 6 + i * 14, y = 11;
        if (i == state.profile) {
            draw_circle(c, x, y, 5, 5, FOREGROUND);
        } else if (state.bonded[i]) {
            draw_circle(c, x, y, 5, 1, FOREGROUND);
        } else {
            draw_rect(c, x - 1, y - 1, 2, 2, FOREGROUND);
        }
    }
    rotate(c);
}

/* Animation
 *
 * Art draws itself: frame 0 is the first stroke and the last frame is the
 * finished picture, which is where it rests. After a layer change it draws
 * once and stays; in "active" mode it redraws every few seconds while you
 * type and rests finished when the keyboard goes idle. */

#define HOLD_TICKS (SWEEP_VIEW_FPS * 3)

static lv_timer_t *anim_timer;
static const struct sweep_view_anim *anim;
static uint8_t anim_frame;
static int anim_hold;
static bool keyboard_active = true;

static void show_frame(uint8_t frame) {
    anim_frame = frame < anim->count ? frame : anim->count - 1;
    lv_image_set_src(art_image, anim->frames[anim_frame]);
}

static void show_finished(void) { show_frame(anim->count - 1); }

static void anim_tick(lv_timer_t *timer) {
    if (!anim) {
        return;
    }
    if (anim_frame + 1 < anim->count) {
        show_frame(anim_frame + 1);
        return;
    }
    if (SWEEP_VIEW_MODE != SWEEP_VIEW_MODE_ACTIVE) {
        lv_timer_pause(timer);
    } else if (++anim_hold >= HOLD_TICKS) {
        anim_hold = 0;
        show_frame(0);
    }
}

static void start_anim(void) {
    anim_hold = 0;
    if (SWEEP_VIEW_MODE == SWEEP_VIEW_MODE_OFF || anim->count < 2 ||
        (SWEEP_VIEW_MODE == SWEEP_VIEW_MODE_ACTIVE && !keyboard_active)) {
        lv_timer_pause(anim_timer);
        show_finished();
        return;
    }
    show_frame(0);
    lv_timer_resume(anim_timer);
}

static void set_layer_art(uint8_t layer) {
    uint8_t index = layer < sweep_view_layer_count ? sweep_view_layer_anim[layer] : 0;
    const struct sweep_view_anim *next = &sweep_view_anims[index < sweep_view_anim_count ? index : 0];
    if (next == anim) {
        return;
    }
    anim = next;
    start_anim();
}

/* Events */

struct battery_state {
    uint8_t level;
    bool usb;
};

static void battery_update(struct battery_state s) {
    state.battery = s.level;
    state.charging = s.usb;
    draw_info();
}

static struct battery_state battery_get(const zmk_event_t *eh) {
    const struct zmk_battery_state_changed *ev = as_zmk_battery_state_changed(eh);
    return (struct battery_state){
        .level = ev ? ev->state_of_charge : zmk_battery_state_of_charge(),
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
        .usb = zmk_usb_is_powered(),
#endif
    };
}

ZMK_DISPLAY_WIDGET_LISTENER(sweep_view_battery, struct battery_state, battery_update, battery_get)
ZMK_SUBSCRIPTION(sweep_view_battery, zmk_battery_state_changed);
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
ZMK_SUBSCRIPTION(sweep_view_battery, zmk_usb_conn_state_changed);
#endif

struct output_state {
    struct zmk_endpoint_instance endpoint;
    int profile;
    bool connected;
    bool bonded;
    bool profiles_bonded[PROFILE_COUNT];
};

static void output_update(struct output_state s) {
    state.endpoint = s.endpoint;
    state.profile = s.profile;
    state.profile_connected = s.connected;
    state.profile_bonded = s.bonded;
    memcpy(state.bonded, s.profiles_bonded, sizeof(state.bonded));
    draw_info();
    draw_profiles();
}

static struct output_state output_get(const zmk_event_t *eh) {
    struct output_state s = {
        .endpoint = zmk_endpoint_get_selected(),
#if IS_ENABLED(CONFIG_ZMK_BLE)
        .profile = zmk_ble_active_profile_index(),
        .connected = zmk_ble_active_profile_is_connected(),
        .bonded = !zmk_ble_active_profile_is_open(),
#endif
    };
#if IS_ENABLED(CONFIG_ZMK_BLE)
    for (int i = 0; i < MIN(PROFILE_COUNT, ZMK_BLE_PROFILE_COUNT); i++) {
        s.profiles_bonded[i] = !zmk_ble_profile_is_open(i);
    }
#endif
    return s;
}

ZMK_DISPLAY_WIDGET_LISTENER(sweep_view_output, struct output_state, output_update, output_get)
ZMK_SUBSCRIPTION(sweep_view_output, zmk_endpoint_changed);
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
ZMK_SUBSCRIPTION(sweep_view_output, zmk_usb_conn_state_changed);
#endif
#if IS_ENABLED(CONFIG_ZMK_BLE)
ZMK_SUBSCRIPTION(sweep_view_output, zmk_ble_active_profile_changed);
#endif

struct layer_state {
    uint8_t index;
    const char *name;
};

static void layer_update(struct layer_state s) {
    state.layer = s.index;
    state.layer_name = s.name;
    draw_info();
    set_layer_art(s.index);
}

static struct layer_state layer_get(const zmk_event_t *eh) {
    zmk_keymap_layer_index_t index = zmk_keymap_highest_layer_active();
    return (struct layer_state){
        .index = index,
        .name = zmk_keymap_layer_name(zmk_keymap_layer_index_to_id(index)),
    };
}

ZMK_DISPLAY_WIDGET_LISTENER(sweep_view_layer, struct layer_state, layer_update, layer_get)
ZMK_SUBSCRIPTION(sweep_view_layer, zmk_layer_state_changed);

/* In "active" mode the art keeps redrawing while you type; once the
 * keyboard goes idle it rests finished, so it costs nothing while you're away. */
struct activity_state {
    enum zmk_activity_state state;
};

static void activity_update(struct activity_state s) {
    const bool was_active = keyboard_active;
    keyboard_active = s.state == ZMK_ACTIVITY_ACTIVE;
    if (SWEEP_VIEW_MODE != SWEEP_VIEW_MODE_ACTIVE || !anim || was_active == keyboard_active) {
        return;
    }
    if (keyboard_active) {
        start_anim();
    } else {
        lv_timer_pause(anim_timer);
        show_finished();
    }
}

static struct activity_state activity_get(const zmk_event_t *eh) {
    const struct zmk_activity_state_changed *ev = as_zmk_activity_state_changed(eh);
    return (struct activity_state){.state = ev ? ev->state : zmk_activity_get_state()};
}

ZMK_DISPLAY_WIDGET_LISTENER(sweep_view_activity, struct activity_state, activity_update,
                            activity_get)
ZMK_SUBSCRIPTION(sweep_view_activity, zmk_activity_state_changed);

/* Setup */

int sweep_view_status_init(lv_obj_t *screen) {
    lv_obj_set_style_bg_color(screen, BACKGROUND, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);

    lv_obj_t *panel = lv_obj_create(screen);
    lv_obj_set_size(panel, 160, 68);
    lv_obj_align(panel, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_bg_color(panel, BACKGROUND, LV_PART_MAIN);

    /* Across the panel: art, then info, then the visible strip of the
     * profile canvas; reversed when the screen is mounted the other way. */
    art_image = lv_image_create(panel);
    info_canvas = lv_canvas_create(panel);
    lv_canvas_set_buffer(info_canvas, info_buf, CANVAS_SIZE, CANVAS_SIZE, CANVAS_FORMAT);
    profile_canvas = lv_canvas_create(panel);
    lv_canvas_set_buffer(profile_canvas, profile_buf, CANVAS_SIZE, CANVAS_SIZE, CANVAS_FORMAT);
#if SWEEP_VIEW_FLIP
    lv_obj_align(art_image, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_align(info_canvas, LV_ALIGN_TOP_LEFT, 68, 0);
    lv_obj_align(profile_canvas, LV_ALIGN_TOP_LEFT, 136, 0);
#else
    lv_obj_align(art_image, LV_ALIGN_TOP_RIGHT, 0, 0);
    lv_obj_align(info_canvas, LV_ALIGN_TOP_LEFT, 24, 0);
    lv_obj_align(profile_canvas, LV_ALIGN_TOP_LEFT, -44, 0);
#endif

    anim_timer = lv_timer_create(anim_tick, 1000 / SWEEP_VIEW_FPS, NULL);
    lv_timer_pause(anim_timer);

    sweep_view_battery_init();
    sweep_view_output_init();
    sweep_view_activity_init();
    sweep_view_layer_init();
    return 0;
}
