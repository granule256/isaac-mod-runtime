#include "infrastructure/content/inflate_rows.hpp"
#include <zlib.h>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <new>
#include <vector>
#include <fstream>
#include <iterator>
#include <cstddef>
namespace {
struct alignas(std::max_align_t) Allocation { std::size_t bytes; bool tracked; };
bool tracking{};std::size_t live{},peak{};long remaining=-1;
void* Allocate(std::size_t n) {
 if(tracking && remaining==0)throw std::bad_alloc();
 if(tracking && remaining>0)--remaining;
 auto* p=static_cast<Allocation*>(std::malloc(sizeof(Allocation)+n));
 if(!p)throw std::bad_alloc();
 p->bytes=n;p->tracked=tracking;
 if(tracking){live+=n;if(live>peak)peak=live;}
 return p+1;
}
void Free(void* p) noexcept {
 if(!p)return;auto* a=static_cast<Allocation*>(p)-1;
 if(a->tracked)live-=a->bytes;
 std::free(a);
}
bool Rows(const uint8_t* src,size_t n,size_t row,size_t count,void* context,isaac::runtime::content::RowSink sink) {
 return isaac::runtime::content::InflateRows<z_stream>(src,n,row,count,context,sink,
  &inflateInit2_,&inflate,&inflateEnd,ZLIB_VERSION);
}
}
void* operator new(std::size_t n){return Allocate(n);}
void* operator new[](std::size_t n){return Allocate(n);}
void operator delete(void* p)noexcept{Free(p);}
void operator delete[](void* p)noexcept{Free(p);}
void operator delete(void* p,std::size_t)noexcept{Free(p);}
void operator delete[](void* p,std::size_t)noexcept{Free(p);}
int main(int argc,char** argv){
 if(argc<3)return 2;
 std::ifstream input(argv[1],std::ios::binary);
 std::vector<uint8_t> png((std::istreambuf_iterator<char>(input)),{});
 if(argc>3)remaining=std::strtol(argv[3],nullptr,10);
 uint8_t* out=nullptr;size_t size=0;
 auto failure=isaac::runtime::content::PngToPcxFailure::None;
 tracking=true;
 const bool ok=isaac::runtime::content::PngToPcxStreaming(png.data(),png.size(),&Rows,&out,&size,&failure);
 tracking=false;
 if(ok){std::ofstream output(argv[2],std::ios::binary);output.write(reinterpret_cast<const char*>(out),size);}
 delete[] out;
 std::printf("ok=%u failure=%u peak=%zu live=%zu input=%zu bytes=%zu\n",ok,unsigned(failure),peak,live,png.size(),size);
 return ok?0:1;
}
