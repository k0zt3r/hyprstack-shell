// Build with wayland-client and the wayland-scanner generated client header
// (virtual-pointer.h) and private code for wlr-virtual-pointer-unstable-v1.xml.
// The test runner points WAYLAND_DISPLAY only at its disposable compositor.
#include <wayland-client.h>
#include <linux/input-event-codes.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "virtual-pointer.h"

static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
    if (!strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name))
        manager = wl_registry_bind(registry, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener listener = {global, removed};

int main(int argc, char **argv) {
    const int drag = argc == 8 && !strcmp(argv[1], "drag");
    const int wheel = argc == 6;
    if (argc != 5 && !wheel && !drag) return 2;
    if (wheel && strcmp(argv[5], "up") && strcmp(argv[5], "down")) return 2;
    const int x = atoi(argv[drag ? 2 : 1]);
    const int y = atoi(argv[drag ? 3 : 2]);
    const int width = atoi(argv[drag ? 6 : 3]);
    const int height = atoi(argv[drag ? 7 : 4]);
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) return 3;
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &listener, NULL);
    wl_display_roundtrip(display);
    if (!manager) return 4;
    struct zwlr_virtual_pointer_v1 *pointer = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager, NULL);
    zwlr_virtual_pointer_v1_motion_absolute(pointer, 1, x, y, width, height);
    zwlr_virtual_pointer_v1_frame(pointer);
    wl_display_roundtrip(display);
    if (wheel) {
        const int direction = !strcmp(argv[5], "up") ? -1 : 1;
        zwlr_virtual_pointer_v1_axis_source(pointer, WL_POINTER_AXIS_SOURCE_WHEEL);
        zwlr_virtual_pointer_v1_axis_discrete(pointer, 2, WL_POINTER_AXIS_VERTICAL_SCROLL,
                                            wl_fixed_from_int(direction * 15), direction);
    } else {
        zwlr_virtual_pointer_v1_button(pointer, 2, BTN_LEFT, WL_POINTER_BUTTON_STATE_PRESSED);
        zwlr_virtual_pointer_v1_frame(pointer);
        wl_display_roundtrip(display);
        if (drag) {
            zwlr_virtual_pointer_v1_motion_absolute(pointer, 3, atoi(argv[4]), atoi(argv[5]), width, height);
            zwlr_virtual_pointer_v1_frame(pointer);
            wl_display_roundtrip(display);
            usleep(30000);
        }
        zwlr_virtual_pointer_v1_button(pointer, 4, BTN_LEFT, WL_POINTER_BUTTON_STATE_RELEASED);
    }
    zwlr_virtual_pointer_v1_frame(pointer);
    wl_display_roundtrip(display);
    if (drag) {
        // Move back over the application immediately after release. A pending
        // live screencopy must keep the selected crop instead of resnapping.
        zwlr_virtual_pointer_v1_motion_absolute(pointer, 5, width / 2, height / 2, width, height);
        zwlr_virtual_pointer_v1_frame(pointer);
        wl_display_roundtrip(display);
    }
    zwlr_virtual_pointer_v1_destroy(pointer);
    zwlr_virtual_pointer_manager_v1_destroy(manager);
    wl_registry_destroy(registry);
    wl_display_disconnect(display);
    return 0;
}
