#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lua.h"
#include "lauxlib.h"
#include "lstate.h"
#include "lgc.h"
#include "lgcbudget.h"

#define CHECK(c) do {if (!(c)) {fprintf(stderr,"%s:%d: %s\n",__func__,__LINE__,#c);exit(1);}} while(0)
typedef struct {size_t live, peak; int fail, failed;} Alloc;
typedef struct {uint64_t tick, cost;} Clock;
static void *alloc(void *ctx,void *ptr,size_t old,size_t n) {
  Alloc *a=ctx; void *r;
  if (!ptr) old=0;
  if (!n) {free(ptr);a->live-=old;return NULL;}
  if(n>old && a->fail) {--a->fail;++a->failed;return NULL;}
  r=realloc(ptr,n);
  if(r) {a->live=a->live-old+n;if(a->live>a->peak)a->peak=a->live;}
  return r;
}
static uint64_t tick(void *ctx) {Clock *c=ctx;c->tick+=c->cost;return c->tick;}
static int panic(lua_State *L) {fprintf(stderr,"PANIC: %s\n",lua_tostring(L,-1));return 0;}
static int noop(lua_State *L) {(void)L;return 0;}
static lua_State *newvm(Alloc *a) {lua_State *L=lua_newstate(alloc,a);CHECK(L);lua_atpanic(L,panic);lua_pushcfunction(L,noop);CHECK(lua_pcall(L,0,0,0)==LUA_OK);return L;}
static void closevm(lua_State *L,Alloc *a) {CHECK(a->live==gettotalbytes(G(L)));lua_close(L);CHECK(a->live==0);}
static int advance(lua_State *L) {lua_gc_advance(L);return 0;}
static int automatic(lua_State *L) {luaC_checkGC(L);return 0;}
static int call(lua_State *L,lua_CFunction f) {lua_pushcfunction(L,f);return lua_pcall(L,0,0,0);}
static void garbage(lua_State *L,int n) {
  int i;lua_gc(L,LUA_GCSTOP,0);
  for(i=0;i<n;++i) {lua_newtable(L);lua_pushinteger(L,i);lua_setfield(L,-2,"n");lua_pop(L,1);}
  lua_gc(L,LUA_GCRESTART,0);luaE_setdebt(G(L),1000000);
}
static void budget(lua_State *L,Clock *c,uint64_t cap,size_t high) {
  lua_gc_setframebudget(L,tick,c,cap,high);lua_gc_beginframe(L,1);
}
static int finalized, nested_mode;
static int finalizer(lua_State *L) {
  ++finalized;
  if(nested_mode==1) return luaL_error(L,"expected-finalizer-error");
  if(nested_mode==2) {
    lua_GCBudgetInfo before, after;
    lua_gc(L,LUA_GCRESTART,0);
    lua_gc_budgetinfo(L,&before);
    lua_newtable(L);lua_pop(L,1);
    CHECK(call(L,automatic)==LUA_OK);CHECK(call(L,advance)==LUA_OK);
    lua_gc_budgetinfo(L,&after);
    CHECK(after.slices==before.slices);CHECK(after.steps==before.steps);
    lua_gc(L,LUA_GCSTEP,0);
    CHECK(call(L,advance)==LUA_OK);
  }
  return 0;
}
static void finalizable(lua_State *L,int n) {
  int i;lua_gc(L,LUA_GCSTOP,0);
  for(i=0;i<n;++i) {
    lua_newuserdata(L,8);lua_newtable(L);lua_pushcfunction(L,finalizer);
    lua_setfield(L,-2,"__gc");lua_setmetatable(L,-2);lua_pop(L,1);
  }
  lua_gc(L,LUA_GCRESTART,0);
}
static void test_shared(void) {
  Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a),*co;
  co=lua_newthread(L);lua_pushcfunction(co,noop);CHECK(lua_pcall(co,0,0,0)==LUA_OK);garbage(L,6000);budget(L,&c,3,0);
  CHECK(call(L,automatic)==LUA_OK);
  {l_mem debt=G(L)->GCdebt;int state=G(L)->gcstate;uint64_t t=c.tick;
   CHECK(debt>0);CHECK(state!=GCSpause);
   CHECK(call(co,automatic)==LUA_OK);CHECK(call(L,advance)==LUA_OK);
   CHECK(G(L)->GCdebt==debt);CHECK(G(L)->gcstate==state);
   CHECK(c.tick==t); /* exhausted quota has no clock-read overhead */
   lua_gc_beginframe(L,1);CHECK(call(L,automatic)==LUA_OK);CHECK(G(L)->GCdebt==debt);
   lua_gc_beginframe(L,2);CHECK(call(L,automatic)==LUA_OK);CHECK(G(L)->GCdebt<debt);
  }
  closevm(L,&a);
}
static void test_continuation(void) {
  Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a);int i;
  garbage(L,6000);budget(L,&c,2,0);CHECK(call(L,automatic)==LUA_OK);
  luaE_setdebt(G(L),-100000); /* no further allocating callbacks */
  lua_gc_beginframe(L,2);CHECK(call(L,advance)==LUA_OK);
  CHECK(G(L)->GCdebt<=-100000);
  for(i=2;i<20000 && G(L)->gcstate!=GCSpause;++i) {
    lua_gc_beginframe(L,i);CHECK(call(L,advance)==LUA_OK);
  }
  CHECK(G(L)->gcstate==GCSpause);CHECK(a.live<200000);
  {uint64_t t=c.tick;lua_gc_beginframe(L,i+1);CHECK(call(L,advance)==LUA_OK);CHECK(c.tick==t);}
  closevm(L,&a);
}
static void test_explicit(void) {
  Alloc a={0};Clock c={0,10};lua_State *L=newvm(&a);l_mem debt;
  garbage(L,3000);budget(L,&c,1,0);CHECK(call(L,automatic)==LUA_OK);
  debt=G(L)->GCdebt;lua_gc(L,LUA_GCSTEP,1);CHECK(G(L)->GCdebt<debt);
  lua_gc(L,LUA_GCSTEP,0);lua_gc(L,LUA_GCSTEP,-1);
  lua_gc(L,LUA_GCCOLLECT,0);CHECK(G(L)->gcstate==GCSpause);CHECK(a.live<100000);
  closevm(L,&a);
}
static void test_stop(void) {
  Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a);l_mem debt;
  garbage(L,1000);budget(L,&c,3,1);lua_gc(L,LUA_GCSTOP,0);debt=G(L)->GCdebt;
  CHECK(call(L,advance)==LUA_OK);CHECK(call(L,automatic)==LUA_OK);
  CHECK(G(L)->GCdebt==debt);CHECK(c.tick==0);
  lua_gc(L,LUA_GCSTEP,0);CHECK(!G(L)->gcrunning);
  lua_gc(L,LUA_GCRESTART,0);luaE_setdebt(G(L),100000);CHECK(call(L,automatic)==LUA_OK);CHECK(c.tick>0);
  closevm(L,&a);
}
static void test_finalizers(void) {
  Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a);int i;
  finalizable(L,90);budget(L,&c,1,0);luaE_setdebt(G(L),100000);
  for(i=1;i<10000 && finalized<90;++i) {
    int prev=finalized;lua_gc_beginframe(L,i);CHECK(call(L,advance)==LUA_OK);CHECK(finalized-prev<=1);
  }
  CHECK(finalized==90);lua_gc(L,LUA_GCCOLLECT,0);CHECK(finalized==90);closevm(L,&a);
}
static void test_gcerror(void) {
  Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a);int i,status=0;
  nested_mode=1;finalizable(L,2);budget(L,&c,1,1);luaE_setdebt(G(L),100000);
  for(i=1;i<1000;++i) {lua_gc_beginframe(L,i);status=call(L,advance);if(status!=LUA_OK)break;}
  CHECK(status==LUA_ERRGCMM);CHECK(strstr(lua_tostring(L,-1),"expected-finalizer-error"));lua_pop(L,1);
  nested_mode=0;CHECK(call(L,advance)==LUA_OK);CHECK(finalized==1);
  lua_gc_beginframe(L,i+1);CHECK(call(L,advance)==LUA_OK);CHECK(finalized==2);closevm(L,&a);
}
static void test_nested(void) {
  Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a);int i;
  nested_mode=2;finalizable(L,10);budget(L,&c,1,1);luaE_setdebt(G(L),100000);
  for(i=1;i<1000 && finalized<10;++i) {lua_gc_beginframe(L,i);CHECK(call(L,advance)==LUA_OK);}
  CHECK(finalized==10);closevm(L,&a);
}
static void test_credit(void) {
  const int multipliers[]={40,150,200,333};int n;
  for(n=0;n<4;++n) {
    Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a);
    garbage(L,1000);luaC_runtilstate(L,bitmask(GCSswpfinobj));
    lua_gc(L,LUA_GCSETSTEPMUL,multipliers[n]);luaE_setdebt(G(L),-100);
    budget(L,&c,1,0);CHECK(call(L,advance)==LUA_OK);
    CHECK(G(L)->GCdebt==-100);closevm(L,&a);
  }
}
static void test_saturation(void) {
  int sign;
  for(sign=-1;sign<=1;sign+=2) {
    Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a);
    garbage(L,1000);luaC_runtilstate(L,bitmask(GCSpropagate));
    lua_gc(L,LUA_GCSETSTEPMUL,INT_MAX);
    luaE_setdebt(G(L),sign*(MAX_LMEM/2));budget(L,&c,1,0);
    CHECK(call(L,advance)==LUA_OK);
    CHECK(a.live==gettotalbytes(G(L)));CHECK(G(L)->gcstate!=GCSpause);
    if(sign<0)CHECK(G(L)->GCdebt<0);
    closevm(L,&a);
  }
}
static void test_pressure(void) {
  Alloc a={0};Clock c={0,1};lua_State *L=newvm(&a);lua_GCBudgetInfo info;int i;
  /* The retained live set itself can exceed the pressure threshold. */
  lua_newuserdata(L,65536);garbage(L,3000);budget(L,&c,3,32768);
  CHECK(call(L,automatic)==LUA_OK);lua_gc_budgetinfo(L,&info);
  CHECK(info.pressure==1);CHECK(info.spent<=3*4+c.cost);
  {uint64_t steps=info.steps,t=c.tick;
   CHECK(call(L,automatic)==LUA_OK);CHECK(call(L,advance)==LUA_OK);
   lua_gc_budgetinfo(L,&info);CHECK(info.steps==steps);CHECK(c.tick==t);}
  for(i=2;i<20000 && !info.cycles;++i) {
    lua_gc_beginframe(L,i);CHECK(call(L,advance)==LUA_OK);
    lua_gc_budgetinfo(L,&info);CHECK(info.spent<=3*4+c.cost);
  }
  CHECK(info.cycles==1);CHECK(a.live>=32768);CHECK(a.live<100000);
  {uint64_t t=c.tick;lua_gc_beginframe(L,i);CHECK(call(L,advance)==LUA_OK);CHECK(c.tick==t);}
  closevm(L,&a);
}
static int allocate(lua_State *L) {lua_newuserdata(L,1024);return 1;}
static void test_oom(void) {
  Alloc a={0};Clock c={0,10};lua_State *L=newvm(&a);size_t old;
  garbage(L,5000);budget(L,&c,1,0);CHECK(call(L,automatic)==LUA_OK);lua_gc(L,LUA_GCSTOP,0);old=a.live;
  a.fail=1;lua_pushcfunction(L,allocate);CHECK(lua_pcall(L,0,1,0)==LUA_OK);
  CHECK(a.failed==1);CHECK(a.live<old);CHECK(lua_isuserdata(L,-1));lua_pop(L,1);
  a.fail=2;CHECK(call(L,allocate)==LUA_ERRMEM);lua_pop(L,1);CHECK(a.failed==3);CHECK(!G(L)->gcrunning);
  closevm(L,&a);
}
static void test_isolation(void) {
  Alloc a={0},b={0};Clock c={0,1};lua_State *L=newvm(&a),*M=newvm(&b);
  garbage(L,3000);garbage(M,3000);budget(L,&c,1,0);CHECK(call(L,automatic)==LUA_OK);
  {l_mem debt=G(M)->GCdebt;CHECK(call(M,automatic)==LUA_OK);CHECK(G(M)->GCdebt<debt);}
  closevm(L,&a);closevm(M,&b);L=newvm(&a);garbage(L,1000);
  {l_mem debt=G(L)->GCdebt;CHECK(call(L,automatic)==LUA_OK);CHECK(G(L)->GCdebt<debt);}
  budget(L,&c,1,0);lua_gc_setframebudget(L,NULL,NULL,0,0);luaE_setdebt(G(L),10000);
  {l_mem debt=G(L)->GCdebt;CHECK(call(L,automatic)==LUA_OK);CHECK(G(L)->GCdebt<debt);}
  closevm(L,&a);
}
int main(int argc,char **argv) {
  const char *names[]={"shared","continuation","explicit","stop","finalizers","gcerror","nested","pressure","oom","isolation","credit","saturation"};
  void (*tests[])(void)={test_shared,test_continuation,test_explicit,test_stop,test_finalizers,test_gcerror,test_nested,test_pressure,test_oom,test_isolation,test_credit,test_saturation};
  int i;CHECK(argc==2);for(i=0;i<12;++i)if(!strcmp(argv[1],names[i])) {tests[i]();puts("PASS");return 0;}return 2;
}
