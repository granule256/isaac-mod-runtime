"""Compile the portable verifier and exercise real platform SHA and byte reads."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "notice_integrity.hpp"
#include <algorithm>
#include <cassert>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>
using namespace isaac::runtime::notice::integrity;
Digest hash(const std::string& v) { Sha256 h; h.Update(v.data(),v.size()); return h.Finish(); }
std::string hex(const Digest& d) { std::string v; for(auto b:d) {v+="0123456789abcdef"[b>>4];v+="0123456789abcdef"[b&15];} return v; }
struct Reader {
 std::map<std::string,std::string> files; const std::string* current=nullptr;
 size_t cursor=0, chunk=8192; unsigned opens=0, closes=0; bool fail=false; int delta=0;
 static ReadStatus open(void* c,const char* p,std::uint64_t* n) {auto& r=*static_cast<Reader*>(c); assert(!r.current); auto f=r.files.find(p);if(f==r.files.end())return ReadStatus::NotFound;r.current=&f->second;r.cursor=0;r.opens++;*n=r.current->size()+r.delta;return ReadStatus::Ok;}
 static ReadStatus read(void* c,void* b,size_t n,size_t* got) {auto& r=*static_cast<Reader*>(c);assert(r.current);if(r.fail)return ReadStatus::IoError;*got=std::min({n,r.chunk,r.current->size()-r.cursor});if(*got)std::memcpy(b,r.current->data()+r.cursor,*got);r.cursor+=*got;return ReadStatus::Ok;}
 static void close(void* c) {auto& r=*static_cast<Reader*>(c); assert(r.current);r.current=nullptr;r.closes++;}
 ReadPort port(){return {this,open,read,close};}
};
const char* manifestPath="rom:/rp_patch/resources/gfx/ui/main menu/isaac-switch/nnotice.manifest";
const std::string pcx="rom:/rp_patch/resources/gfx/ui/main menu/isaac-switch/nnotice_en.pcx";
const std::string anm="rom:/rp_patch/resources/gfx/ui/main menu/isaac-switch/nnotice_en.anm2";
std::string row(const std::string& p,const std::string& v) {return std::to_string(v.size())+"\t"+hex(hash(v))+"\t"+p+"\n";}
std::string manifest(const Reader& r) {return "ISAAC-NOTICE/1\nv1.0.0-beta.4\n"+row(anm,r.files.at(anm))+row(pcx,r.files.at(pcx));}
int main() {
 assert(hex(hash(""))=="EMPTY");assert(hex(hash("abc"))=="ABC");assert(hex(hash("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"))=="LONG");
 std::string chunks;for(unsigned i=0;i<20003;i++)chunks+=char(i%251);Sha256 sha;for(size_t i=0;i<chunks.size();i+=63)sha.Update(chunks.data()+i,std::min<size_t>(63,chunks.size()-i));assert(hex(sha.Finish())=="CHUNKS");
 Reader r; r.files[pcx]=chunks;r.files[anm]="anm bytes";const auto good=manifest(r);r.files[manifestPath]=good;const auto root=hash(good);static Manifest out;
 auto check=[&](Failure expected,unsigned count=2) {auto v=VerifyPackage(r.port(),manifestPath,root,"v1.0.0-beta.4",count,out);assert(v.failure==expected);assert(r.opens==r.closes);return v;};
 assert(check(Failure::None).bytesRead==good.size()+chunks.size()+9);assert(out.count==2);
 r.chunk=7;check(Failure::None);r.chunk=8192;
 r.files[pcx][4]^=1;check(Failure::ResourceDigest);r.files[pcx]=chunks;
 r.files[anm][1]^=1;check(Failure::ResourceDigest);r.files[anm]="anm bytes";
 r.files.erase(pcx);check(Failure::ResourceMissing);r.files[pcx]=chunks;
 r.files[pcx].pop_back();check(Failure::ResourceSize);r.files[pcx]=chunks+"x";check(Failure::ResourceSize);r.files[pcx]=chunks;
 r.files.erase(manifestPath);check(Failure::ManifestMissing);r.files[manifestPath]=good;
 r.files[manifestPath][0]^=1;check(Failure::ManifestDigest);r.files[manifestPath]=good;
 check(Failure::ManifestFormat,3);check(Failure::ManifestFormat,0);check(Failure::ManifestFormat,65);r.fail=true;check(Failure::ManifestRead);r.fail=false;
 r.files[manifestPath]=std::string(kMaxManifestBytes+1,'x');check(Failure::ManifestRead);r.files[manifestPath]=good;
 auto bad=[&](std::string text) {r.files[manifestPath]=text;auto v=VerifyPackage(r.port(),manifestPath,hash(text),"v1.0.0-beta.4",2,out);assert(v.failure==Failure::ManifestFormat);assert(r.opens==r.closes);};
 bad("ISAAC-NOTICE/1\nwrong\n"+row(anm,"anm bytes")+row(pcx,chunks));
 bad("ISAAC-NOTICE/1\nv1.0.0-beta.4\n"+row(pcx,chunks)+row(pcx,chunks));
 bad("ISAAC-NOTICE/1\nv1.0.0-beta.4\n"+row(anm,"anm bytes")+row("rom:/rp_patch/resources/../nnotice_en.pcx",chunks));
 bad(good+"junk");bad(good.substr(0,good.size()-1));
 auto text=good;text[text.find('\t')-1]='x';bad(text);
 text=good;text.insert(text.find('\t'),"18446744073709551616");bad(text);
 text=good;text[text.find('\t')+1]='A';bad(text);
 text=good;text[text.find("rom:")]='\0';bad(text);
 text=good;text.insert(text.find('\n'),"\r");bad(text);
 text=good;text.replace(text.find("resources/gfx"),13,"resources\\gfx");bad(text);
 text=good;text.replace(text.find("nnotice_en.anm2"),14,"nnotice_xx.anm2");bad(text);
 r.files[manifestPath]=good;check(Failure::None);
 auto e=out.entries[1];r.fail=true;assert(VerifyEntry(r.port(),e).failure==Failure::ResourceRead);r.fail=false;r.delta=1;assert(VerifyEntry(r.port(),e).failure==Failure::ResourceSize);r.delta=-1;assert(VerifyEntry(r.port(),e).failure==Failure::ResourceSize);r.delta=0;
 // A reported length larger than actual bytes must fail on the first zero read.
 e.size++;r.delta=1;assert(VerifyEntry(r.port(),e).failure==Failure::ResourceRead);r.delta=0;
 assert(r.opens==r.closes);ReadPort invalid{};assert(VerifyEntry(invalid,e).failure==Failure::InvalidPort);assert(VerifyPackage(invalid,manifestPath,root,"v1.0.0-beta.4",2,out).failure==Failure::InvalidPort);
 std::cout<<"SHA vectors, streamed digest, parser, mutations, missing/size/read/close checks passed\n";
}
'''

class NoticeIntegrityTests(unittest.TestCase):
    def test_portable_verifier(self):
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler)
        source = HARNESS
        for name, data in [('EMPTY',b''),('ABC',b'abc'),('LONG',b'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'),('CHUNKS', bytes(i%251 for i in range(20003)))]:
            source=source.replace('"'+name+'"','"'+hashlib.sha256(data).hexdigest()+'"')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'test.cpp').write_text(source)
            cmd=[compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(path/'test.cpp'),str(ROOT/'runtime/source/program/notice_integrity.cpp'),str(ROOT/'runtime/source/program/notice_integrity_hash.cpp'),'-o',str(path/'test')]
            if sys.platform!='darwin':cmd+=['-lcrypto']
            compiled=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('checks passed',result.stdout)

if __name__=='__main__':unittest.main()
