#include "panel_model.h"
#include <string.h>
void panel_put32(uint8_t *p,uint32_t v){unsigned i;for(i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
uint32_t panel_get32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put16(uint8_t *p,int v){p[0]=(uint8_t)v;p[1]=(uint8_t)((unsigned)v>>8);}
static unsigned step(unsigned v,int d,unsigned n,unsigned lo,unsigned hi){
 if(d<0)return v<=lo || v-lo<n?lo:v-n;
 return v>=hi || hi-v<n?hi:v+n;
}
static void position(const panel_model *m,unsigned focus,int *x,int *y){
 if(focus==0){*x=3;*y=1;return;}
 if(focus<=2){*x=focus==1?12:24;*y=3;return;}
 focus-=3;*x=5;
 if(m->page==0){*x=focus==2?47:5;*y=focus==2?20:focus==1?21:19;}
 else if(m->page==1)*y=5+(int)focus*2;
 else if(m->page==2)*y=5+(int)focus*2;
 else if(m->page==3){*x=focus==0?3:focus==1?17:focus==2?33:47;*y=19;}
 else *y=9;
}
void panel_move(panel_model *m,panel_navigation *nav,unsigned key){
 if(nav->editing){
  if(key==KEY_OK){
   panel_model *v=&nav->draft;unsigned f=v->field;
   if(m->page==0){if(f==0)m->timebase=v->timebase;else m->gain=v->gain;}
   else if(m->page==1){
    switch(f){
     case 0:m->mode=v->mode;break;case 1:m->kind=v->kind;break;
     case 2:m->level=v->level;break;case 3:m->hysteresis=v->hysteresis;break;
     case 4:m->low=v->low;break;case 5:m->high=v->high;break;
     case 6:m->width_min=v->width_min;break;case 7:m->width_max=v->width_max;break;
     case 8:m->limit=v->limit;break;case 9:m->observation=v->observation;break;
     default:m->pre=v->pre;break;
    }m->dirty=1;m->revision++;
   }else if(m->page==2){
    switch(f){
     case 0:m->enable=v->enable;break;case 1:m->wave=v->wave;break;
     case 2:m->hz=v->hz;break;case 3:m->phase=v->phase;break;
     case 4:m->amplitude=v->amplitude;break;default:m->offset=v->offset;break;
    }m->dirty=1;m->revision++;
   }else if(m->page==3){
    if(f==0)m->x1=v->x1;else if(f==1)m->x2=v->x2;else if(f==2)m->y1=v->y1;else m->y2=v->y2;
   }
   nav->editing=0;return;
  }
  panel_key(&nav->draft,4,(key==KEY_LEFT || key==KEY_DOWN)?-1:1,key==KEY_UP || key==KEY_DOWN);
  return;
 }
 if(key!=KEY_OK){
  int x,y,best=100000;unsigned i,chosen=nav->focus;
  if(m->page==0){
   if(key==KEY_RIGHT && (nav->focus==3 || nav->focus==4)){nav->focus=5;return;}
   if(key==KEY_LEFT && nav->focus==5){nav->focus=3;return;}
   if(key==KEY_DOWN && nav->focus==3){nav->focus=4;return;}
   if(key==KEY_UP && nav->focus==4){nav->focus=3;return;}
   if(key==KEY_UP && nav->focus==5){nav->focus=2;return;}
   if(key==KEY_DOWN && nav->focus==5)return;
  }
  if(nav->focus==0 && (key==KEY_LEFT || key==KEY_RIGHT)){
   nav->target_page=(nav->target_page+(key==KEY_LEFT?5:1))%6;return;
  }
  position(m,nav->focus,&x,&y);
  for(i=0;i<panel_visible_fields(m)+3;i++){
   int xx,yy,axis,other,score;position(m,i,&xx,&yy);
   if(key==KEY_UP || key==KEY_DOWN){axis=key==KEY_UP?y-yy:yy-y;other=xx>x?xx-x:x-xx;}
   else {if(yy!=y)continue;axis=key==KEY_LEFT?x-xx:xx-x;other=0;}
   if(axis<=0)continue;
   score=axis*100+other;if(score<best){best=score;chosen=i;}
  }
  nav->focus=chosen;
  return;
 }
 if(key!=KEY_OK)return;
 if(nav->focus==0){m->page=nav->target_page;m->field=0;return;}
 if(nav->focus==1){panel_key(m,0,1,0);return;}
 if(nav->focus==2){panel_key(m,1,1,0);return;}
 m->field=panel_field_index(m,nav->focus-3);
 if((m->page==0 && m->field==2) || m->page==5){panel_key(m,4,1,0);return;}
 if(m->page==4)return;
 nav->draft=*m;nav->editing=1;
}
static int signed_step(int v,int d,unsigned n,int lo,int hi){
 int r=v+d*(int)n;return r<lo?lo:r>hi?hi:r;
}
unsigned panel_fields(unsigned p){static const unsigned n[]={3,11,6,4,0,1};return n[p%6];}
unsigned panel_visible_fields(const panel_model *m){
 if(m->page!=1)return panel_fields(m->page);
 return (m->kind>=2 && m->kind<=7)?7:5;
}
unsigned panel_field_index(const panel_model *m,unsigned visible){
 static const unsigned core[]={0,1,2,3,10};
 if(m->page!=1)return visible;
 if(visible<5)return core[visible];
 return (m->kind<=3?4:m->kind<=5?6:8)+(visible-5);
}
void panel_init(panel_model *m){
 memset(m,0,sizeof *m);m->running=1;m->gain=3;m->pre=50;m->low=-100;m->high=100;
 m->hysteresis=8;m->width_min=25;m->width_max=25000;m->limit=100;m->observation=256;
 m->hz=1000000;m->amplitude=4096;m->enable=1;m->x1=160;m->x2=480;m->y1=120;m->y2=200;m->dirty=1;
}
void panel_autoscale(panel_model *m,uint32_t vpp,uint32_t hz){
 m->gain=vpp<=800?3:vpp<=1600?2:vpp<=3200?1:0;
 m->timebase=hz>=500000?0:hz>=125000?1:hz>=25000?2:hz>=6000?3:4;
}
void panel_key(panel_model *m,unsigned key,int d,unsigned coarse){
 unsigned n=coarse?10:1,f=m->field;
 if(key==0){m->running=m->single?0:!m->running;m->single=0;m->dirty=1;}
 else if(key==1){m->running=0;m->single=1;m->dirty=1;}
 else if(key==2){m->page=(m->page+1)%6;m->field=0;return;}
 else if(key==3){m->field=(f+1)%panel_fields(m->page);return;}
 else if(key==4){
  switch(m->page){
   case 0:if(f==0)m->timebase=step(m->timebase,d,1,0,4);
    else if(f==1)m->gain=step(m->gain,d,1,0,3);else m->selftest=3;
    return;
   case 1:
    switch(f){
     case 0:m->mode=step(m->mode,d,1,0,2);break;
     case 1:m->kind=step(m->kind,d,1,0,8);break;
     case 2:m->level=signed_step(m->level,d,coarse?100:1,-2048,2047);break;
     case 3:m->hysteresis=step(m->hysteresis,d,n,0,(unsigned)(m->high-m->low-1)/2);break;
     case 4:m->low=signed_step(m->low,d,coarse?100:1,-2048,m->high-(int)(2*m->hysteresis)-1);break;
     case 5:m->high=signed_step(m->high,d,coarse?100:1,m->low+(int)(2*m->hysteresis)+1,2047);break;
     case 6:m->width_min=step(m->width_min,d,n,1,m->width_max);break;
     case 7:m->width_max=step(m->width_max,d,coarse?1000:1,m->width_min,25000000);break;
     case 8:m->limit=step(m->limit,d,coarse?100:1,0,4095);break;
     case 9:m->observation=step(m->observation,d,coarse?100:1,2,16384);break;
     default:m->pre=step(m->pre,d,n,0,100);break;
    }break;
   case 2:switch(f){
    case 0:m->enable=!m->enable;break;
    case 1:m->wave=(m->wave+(d<0?1u:3u))&3u;break;
    case 2:m->hz=step(m->hz,d,n*1000,0,12500000);break;
    case 3:m->phase=step(m->phase,d,n,0,359);break;
    case 4:m->amplitude=step(m->amplitude,d,coarse?160:1,0,8191);break;
    default:m->offset=signed_step(m->offset,d,coarse?160:1,-8192,8191);break;
   }break;
   case 3:if(f==0)m->x1=step(m->x1,d,n,0,639);else if(f==1)m->x2=step(m->x2,d,n,0,639);
    else if(f==2)m->y1=step(m->y1,d,n,0,279);else m->y2=step(m->y2,d,n,0,279);
    return;
   case 5:m->selftest=1;return;
   default:return;
  }
  m->dirty=1;
 }
 if(m->dirty)m->revision++;
}
void panel_trigger(const panel_model *m,uint8_t p[24]){
 memset(p,0,24);p[0]=(uint8_t)m->kind;put16(p+2,m->level);put16(p+4,(int)m->hysteresis);
 put16(p+6,m->low);put16(p+8,m->high);panel_put32(p+10,m->width_min);panel_put32(p+14,m->width_max);
 put16(p+18,(int)m->limit);panel_put32(p+20,m->observation);
}
