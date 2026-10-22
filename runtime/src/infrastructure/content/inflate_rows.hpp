#pragma once
#include "infrastructure/content/png_to_pcx_bridge.hpp"
#include <cstdint>
#include <memory>
#include <new>
namespace isaac::runtime::content {
// 与设备112字节z_stream和宿主zlib共用执行逻辑，zlib内部工作区由原分配器管理。
template<class Stream,class Init,class Inflate,class End>
bool InflateRows(const uint8_t* src,size_t length,size_t rowBytes,size_t rows,void* context,
                 RowSink sink,Init init,Inflate inflate,End end,const char* version) noexcept {
    if(!src || !sink || !rowBytes || !rows || length>UINT32_MAX || rowBytes>UINT32_MAX) return false;
    std::unique_ptr<uint8_t[]> row(new (std::nothrow) uint8_t[rowBytes]);
    if(!row) return false;
    Stream stream{};
    stream.next_in=const_cast<uint8_t*>(src); stream.avail_in=static_cast<uint32_t>(length);
    if(init(&stream,15,version,sizeof(Stream))!=0) return false;
    bool ok=true; bool finished=false;
    for(size_t y=0;y<rows && ok;++y) {
        stream.next_out=row.get(); stream.avail_out=static_cast<uint32_t>(rowBytes);
        while(stream.avail_out && ok) {
            auto input=stream.avail_in; auto output=stream.avail_out;
            int result=inflate(&stream,0);
            if(result==1) { finished=true; if(stream.avail_out || y+1!=rows) ok=false; break; }
            if(result!=0 || (input==stream.avail_in && output==stream.avail_out)) ok=false;
        }
        if(ok && !sink(context,row.get(),rowBytes)) ok=false;
    }
    // 行数恰好写满时，仍须消费checksum；多一个解压字节就是尺寸不符。
    if(ok && !finished) {
        uint8_t extra=0; stream.next_out=&extra; stream.avail_out=1;
        int result=inflate(&stream,0);
        ok=result==1 && stream.avail_out==1;
        finished=result==1;
    }
    ok=ok && finished && stream.avail_in==0;
    if(end(&stream)!=0) ok=false;
    return ok;
}
}
