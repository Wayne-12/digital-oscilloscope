#ifndef PANEL_MODEL_H
#define PANEL_MODEL_H
#include <stdint.h>
typedef struct {
 unsigned page,field,running,single,timebase,gain,mode,kind,pre;
 int level,low,high;unsigned hysteresis,width_min,width_max,limit,observation;
 unsigned wave,enable,hz,phase,amplitude;int offset;
 unsigned x1,x2,y1,y2,dirty,revision,selftest,result;
} panel_model;
enum {KEY_UP,KEY_DOWN,KEY_LEFT,KEY_RIGHT,KEY_OK};
typedef struct {unsigned focus,editing,target_page;panel_model draft;} panel_navigation;
void panel_move(panel_model *m,panel_navigation *nav,unsigned key);
void panel_init(panel_model *m);
void panel_key(panel_model *m,unsigned key,int direction,unsigned coarse);
void panel_autoscale(panel_model *m,uint32_t vpp,uint32_t hz);
unsigned panel_fields(unsigned page);
unsigned panel_visible_fields(const panel_model *m);
unsigned panel_field_index(const panel_model *m,unsigned visible);
void panel_trigger(const panel_model *m,uint8_t p[24]);
void panel_put32(uint8_t *p,uint32_t v);
uint32_t panel_get32(const uint8_t *p);
#endif
