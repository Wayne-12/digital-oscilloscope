#ifndef PANEL_KNOB_SCALE_H
#define PANEL_KNOB_SCALE_H
#include <stdint.h>
#define PANEL_KNOB_MIN_MV 108u
#define PANEL_KNOB_MAX_MV 2212u
#define PANEL_KNOB_STEPS 360u
static inline unsigned panel_knob_position(uint32_t mv){
 if(mv<=PANEL_KNOB_MIN_MV)return 0;
 if(mv>=PANEL_KNOB_MAX_MV)return PANEL_KNOB_STEPS;
 return (unsigned)(((mv-PANEL_KNOB_MIN_MV)*PANEL_KNOB_STEPS+
  (PANEL_KNOB_MAX_MV-PANEL_KNOB_MIN_MV)/2)/(PANEL_KNOB_MAX_MV-PANEL_KNOB_MIN_MV));
}
#endif
