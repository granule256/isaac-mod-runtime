#include "infrastructure/internal/internal_hook_adapter.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "room_spawn_internal_hook.hpp"
#include "clear_award_internal_hook.hpp"
#include "clear_award_internal_guards.hpp"
#include "entity_remove_hook.hpp"
#include "entity_remove_guards.hpp"
#include "cold_callbacks_internal_hook.hpp"
#include "cold_callbacks_guards.hpp"
#include "console_callback_hook.hpp"
#include "pressure_plate_animation_hook.hpp"
#include "pressure_plate_internal_guards.hpp"
#include "console_callback_guards.hpp"
#include "trinket_internal_hook.hpp"
#include "trinket_internal_guards.hpp"
#include "runtime_constants.hpp"
#include <array>
#include <cstring>

namespace isaac::runtime {
namespace {
RoomSpawnNativeBindings s_Native{};
ColdCallbackNativeBindings s_ColdCallbackNative{};
std::uintptr_t s_ColdCallbackNativeBase{};
ConsoleUnknownBindings s_ConsoleLength{},s_ConsoleCompare{};
std::uintptr_t s_ConsoleBase{};
ClearAwardNativeBindings s_ClearAwardNative{};
EntityRemoveNativeBindings s_EntityDestructorNative{};
std::uintptr_t s_EntityDestructorBase{};
std::uintptr_t s_ClearAwardNativeBase{};
PressurePlateNativeBindings s_PressureNative{};
std::uintptr_t s_PressureNativeBase{};
TrinketNativeBindings s_TrinketNative{};
std::uintptr_t s_TrinketNativeBase{}; // 安装期只初始化一次，发布后不再写共享绑定。
constexpr std::array<std::uint8_t,16> kNormal = {0x1F,0x15,0x00,0x71,0x81,0x02,0x00,0x54,0x68,0x0A,0x40,0x79,0x1F,0xB5,0x04,0x71};
constexpr std::array<std::uint8_t,8> kSpecial = {0x28,0x04,0x80,0x52,0x68,0x02,0x00,0xB9};
struct Guard { std::uintptr_t offset; std::array<std::uint8_t,16> bytes; };
constexpr Guard kGuards[] = {
    {0x452948, {0xFF,0x83,0x02,0xD1,0xFD,0x7B,0x04,0xA9,0xFD,0x03,0x01,0x91,0xFC,0x6F,0x05,0xA9}},
    {0x452968, {0xF9,0x03,0x02,0x2A,0xF3,0x03,0x01,0xAA,0xF5,0x03,0x00,0xAA,0xA0,0x43,0x00,0xD1}},
    {0x452978, {0xE1,0x03,0x03,0x2A,0xE2,0x00,0x80,0x52,0xF7,0x03,0x03,0x2A,0x27,0x75,0x08,0x94}},
    {0x452988, {0x68,0x02,0x40,0xB9,0xDC,0x32,0x00,0xD0,0x1F,0x09,0x16,0x71,0x9C,0x4F,0x43,0xF9}},
    {0x452998, {0x80,0x08,0x00,0x54,0x1F,0xE1,0x15,0x71,0x41,0x01,0x00,0x54,0x28,0x04,0x80,0x52}},
    {0x4529A8, {0x01,0x05,0x80,0x52,0x68,0x02,0x00,0xB9,0xA0,0x43,0x00,0xD1,0x1F,0x75,0x08,0x94}},
    {0x4529B8, {0x1F,0x00,0x00,0x71,0xE8,0x17,0x9F,0x1A,0x68,0x0A,0x00,0x79,0x68,0x02,0x40,0xB9}},
    {0x4529D8, {0xA1,0x02,0x00,0x54,0x88,0x25,0x80,0x52,0x68,0x0A,0x00,0x79,0x88,0x03,0x40,0xF9}},
    {0x4529E8, {0x09,0x58,0x88,0x52,0x49,0x00,0xA0,0x72,0xA0,0x43,0x00,0xD1,0x14,0x01,0x09,0x8B}},
    {0x4529F8, {0x26,0x75,0x08,0x94,0xE1,0x03,0x00,0x2A,0xE0,0x03,0x14,0xAA,0xE2,0x03,0x1F,0x2A}},
    {0x452A08, {0x23,0x00,0x80,0x52,0x24,0x00,0x80,0x52,0x68,0x86,0x08,0x94,0x68,0x02,0x40,0xB9}},
    {0x452A18, {0x60,0x0E,0x00,0x79,0x1F,0x19,0x00,0x71,0x20,0x0D,0x00,0x54,0x1F,0x15,0x00,0x71}},
    {0x452AA8, {0x28,0x04,0x80,0x52,0x68,0x02,0x00,0xB9,0x28,0x00,0x80,0x52,0x68,0x0A,0x00,0x79}},
    {0x452A1C, {0x1F,0x19,0x00,0x71,0x20,0x0D,0x00,0x54,0x1F,0x15,0x00,0x71,0x81,0x04,0x00,0x54}},
    {0x453798, {0xA0,0x43,0x00,0xD1,0xA9,0x71,0x08,0x94,0xF4,0x4F,0x49,0xA9,0xF6,0x57,0x48,0xA9}},
    // 只核PLT本身；GOT真实目标允许由引擎/已登记挂点解析，不把合法回调拦截当指纹不符。
    {0x66FE90, {0x70,0x21,0x00,0xD0,0x11,0x5A,0x47,0xF9,0x10,0xC2,0x3A,0x91,0x20,0x02,0x1F,0xD6}},
    {0x6743B0, {0x70,0x21,0x00,0x90,0x11,0xA2,0x40,0xF9,0x10,0x02,0x05,0x91,0x20,0x02,0x1F,0xD6}},
    {0x66FE20, {0x70,0x21,0x00,0xD0,0x11,0x3E,0x47,0xF9,0x10,0xE2,0x39,0x91,0x20,0x02,0x1F,0xD6}},
    {0x66FE30, {0x70,0x21,0x00,0xD0,0x11,0x42,0x47,0xF9,0x10,0x02,0x3A,0x91,0x20,0x02,0x1F,0xD6}},
};
bool AddressValid(const HookTarget& target, std::uintptr_t offset, std::size_t bytes) {
    return target.base != 0 && offset <= target.codeSize && bytes <= target.codeSize-offset &&
        target.base <= UINTPTR_MAX-offset-bytes &&
        engine_memory::EngineMemoryReadable(target.base+offset,bytes);
}
bool TrinketGuardsMatch(const HookTarget& target, bool firstInstalled, bool selectedInstalled) {
    if (!AddressValid(target,kTrinketGetFunctionOffset,trinket::kOriginalFunction.size())) return false;
    const auto* function = static_cast<const std::uint8_t*>(
        engine_memory::AsObject(target.base+kTrinketGetFunctionOffset));
    for (std::size_t offset=0; offset<trinket::kOriginalFunction.size(); offset+=4) {
        std::uint32_t expected{};
        std::memcpy(&expected,trinket::kOriginalFunction.data()+offset,4);
        const auto site = kTrinketGetFunctionOffset+offset;
        if ((firstInstalled && site==kTrinketFirstRandomHookOffset) ||
            (selectedInstalled && site==kTrinketSelectedHookOffset)) {
            const auto veneer = site==kTrinketFirstRandomHookOffset ?
                kTrinketFirstVeneerOffset : kTrinketSelectedVeneerOffset;
            if (!relay::BuildInternalBranch(&expected,target.base+site,target.base+veneer)) return false;
        }
        std::uint32_t actual{};
        std::memcpy(&actual,function+offset,4);
        if (actual!=expected) return false;
    }
    for (const auto& guard:trinket::kNativeGuards) {
        if (!AddressValid(target,guard.offset,guard.bytes.size()) ||
            std::memcmp(engine_memory::AsObject(target.base+guard.offset),guard.bytes.data(),guard.bytes.size()))
            return false;
    }
    return true;
}
}
namespace {
template<std::size_t N> bool ColdFunctionGuard(const HookTarget& target,std::uintptr_t offset,
    const std::array<std::uint8_t,N>& original,std::uintptr_t coldSource,std::uintptr_t gate,
    bool firstInstalled) {
    if (target.buildId!=kTargetBuildId || !AddressValid(target,offset,N) || !AddressValid(target,gate,32)) return false;
    for(std::size_t i=0;i<N;i+=4) {
        std::uint32_t expected{},actual{};std::memcpy(&expected,original.data()+i,4);
        const auto site=offset+i;
        if(site==coldSource) {if(!relay::BuildInternalBranch(&expected,target.base+site,target.base+gate))return false;}
        if(offset==kPickupSelectionFunctionOffset && site==kPickupSelectionSpecialOffset) {
            if(!relay::BuildInternalBranch(&expected,target.base+site,target.base+kPickupSelectionSpecialRelayCodeOffset))return false;
        }
        if(offset==kPickupSelectionFunctionOffset && site==kPickupSelectionHookOffset) {
            if(!relay::BuildInternalBranch(&expected,target.base+site,target.base+kPickupSelectionStaticRelayCodeOffset))return false;
        }
        if(firstInstalled && site==kLevelCurseFirstRandomOffset) {
            if(!relay::BuildInternalBranch(&expected,target.base+site,target.base+kLevelCurseFirstVeneerOffset))return false;
        }
        std::memcpy(&actual,engine_memory::AsObject(target.base+site),4);
        if(actual!=expected)return false;
    }
    std::uint32_t replay{},back{};
    std::memcpy(&replay,original.data()+coldSource-offset,4);
    if(!relay::BuildInternalBranch(&back,target.base+gate+20,target.base+coldSource+4))return false;
    const std::uint32_t words[6]={0x100000D0,0xC8DFFE10,0xB4000050,0xD61F0200,replay,back};
    return std::memcmp(engine_memory::AsObject(target.base+gate),words,24)==0;
}
}
Status InternalHookAdapter::Install(HookId id, const HookTarget& target) noexcept {
    if(id==HookId::ConsoleUnknownLength || id==HookId::ConsoleUnknownCompare) {
        const bool compare=id==HookId::ConsoleUnknownCompare;
        auto& installed=compare?consoleCompareInstalled_:consoleLengthInstalled_;
        if(installed)return Status{StatusCode::InvalidState};
        if(target.buildId!=kTargetBuildId || !AddressValid(target,0x3D740,console_callbacks::kRunCommandOriginal.size()) ||
           !AddressValid(target,0x3BFB4,16))return Status{StatusCode::Rejected};
        for(std::size_t i=0;i<console_callbacks::kRunCommandOriginal.size();i+=4) {
            std::uint32_t expected{};std::memcpy(&expected,console_callbacks::kRunCommandOriginal.data()+i,4);
            const auto offset=0x3D740+i;
            if(offset==0x41878 || offset==0x41898) {
                if(!relay::BuildInternalBranch(&expected,target.base+offset,target.base+(offset==0x41878?0x68CD40:0x68CD80)))return Status{StatusCode::Rejected};
            }
            if(std::memcmp(engine_memory::AsObject(target.base+offset),&expected,4))return Status{StatusCode::Rejected};
        }
        if(std::memcmp(engine_memory::AsObject(target.base+0x3BFB4),console_callbacks::kPrintEntry.data(),16))return Status{StatusCode::Rejected};
        if(s_ConsoleBase && s_ConsoleBase!=target.base)return Status{StatusCode::Rejected};
        if(!s_ConsoleBase) {
            s_ConsoleLength={false,engine_call::AsFunction<ConsoleCommandView::Print>(target.base+0x3BFB4)};
            s_ConsoleCompare={true,s_ConsoleLength.print};s_ConsoleBase=target.base;
        }
        relay::InternalHookBinding b{};
        b.callback=ConsoleUnknownInternalCallback;b.user=compare?&s_ConsoleCompare:&s_ConsoleLength;
        b.resumeCount=2;b.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
        b.resumes[0]=target.base+0x41D64;b.resumes[1]=target.base+(compare?0x4189C:0x4187C);
        const relay::ColdInternalHookSite site{target.base+(compare?0x41898:0x41878),target.base+(compare?0x68CD80:0x68CD40),compare?0x35002660U:0x54002761U};
        const auto result=relay::TryInstallConsoleConditionalHook(b,site);
        lastFailure_=static_cast<std::uint32_t>(result);
        if(result!=relay::InternalHookFailure::None)return Status{StatusCode::Rejected};
        installed=true;return Status::Ok();
    }
    lastFailure_ = 0;
    if(id==HookId::LevelCurseFirstRandom || id==HookId::LevelCurseEvaluation || id==HookId::PickupSelection || id==HookId::PickupSelectionSpecial) {
        const bool special=id==HookId::PickupSelectionSpecial;
        const bool pickup=id==HookId::PickupSelection || special,first=id==HookId::LevelCurseFirstRandom;
        bool& installed=pickup?(special?pickupSelectionSpecialInstalled_:pickupSelectionInstalled_):(first?levelCurseFirstInstalled_:levelCurseEvaluationInstalled_);
        if(installed)return Status{StatusCode::InvalidState};
        const auto source=pickup?(special?kPickupSelectionSpecialOffset:kPickupSelectionHookOffset):kLevelCurseEvalOffset;
        const auto gate=pickup?(special?kPickupSelectionSpecialRelayCodeOffset:kPickupSelectionStaticRelayCodeOffset):kLevelCurseStaticRelayCodeOffset;
        const bool guarded=pickup?ColdFunctionGuard(target,kPickupSelectionFunctionOffset,
            cold_callbacks::kPickupInitOriginal,source,gate,false):ColdFunctionGuard(target,kLevelCurseFunctionOffset,
            cold_callbacks::kLevelInitOriginal,source,gate,levelCurseFirstInstalled_);
        if(!guarded || (first && (!AddressValid(target,kLevelCurseFirstVeneerOffset,8) || !AddressValid(target,kLevelCurseFirstPointerSlotOffset,8) || !AddressValid(target,0x66FE30,16)))) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);return Status{StatusCode::Rejected};
        }
        if(first) {
            const std::uint8_t randomPlt[16]={0x70,0x21,0x00,0xD0,0x11,0x42,0x47,0xF9,0x10,0x02,0x3A,0x91,0x20,0x02,0x1F,0xD6};
            if(std::memcmp(engine_memory::AsObject(target.base+0x66FE30),randomPlt,16)) {
                lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);return Status{StatusCode::Rejected};
            }
        }
        if(s_ColdCallbackNativeBase==0) {
            s_ColdCallbackNative.random=engine_call::AsFunction<ColdCallbackNativeBindings::Random>(target.base+0x66FE30);
            s_ColdCallbackNativeBase=target.base;
        } else if(s_ColdCallbackNativeBase!=target.base) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);return Status{StatusCode::Rejected};
        }
        relay::InternalHookBinding b{};
        b.callback=pickup?PickupSelectionInternalCallback:(first?LevelCurseFirstRandomInternalCallback:LevelCurseEvaluateInternalCallback);
        b.user=&s_ColdCallbackNative;b.resumeCount=1;b.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
        relay::InternalHookFailure failure{};
        if(first) {
            b.resumes[0]=target.base+kLevelCurseFirstResumeOffset;
            const relay::InternalHookSite site{target.base+kLevelCurseFirstRandomOffset,kLevelCurseFirstRandomExpectedWord,relay::InternalVeneerKind::Literal8,target.base+kLevelCurseFirstPointerSlotOffset};
            failure=relay::TryInstallInternalHook(b,site,target.base+kLevelCurseFirstVeneerOffset);
        } else {
            b.resumes[0]=target.base+gate+16;
            const relay::ColdInternalHookSite site{target.base+source,target.base+gate,pickup?(special?0xB85FC3B4U:0x7100A29FU):0xF9400309U};
            failure=relay::TryInstallPreinstalledInternalHook(b,site);
        }
        lastFailure_=static_cast<std::uint32_t>(failure);
        if(failure!=relay::InternalHookFailure::None)return Status{StatusCode::Rejected};
        installed=true;return Status::Ok();
    }
    if(id==HookId::PressurePlateDestructor||id==HookId::PressurePlateDeletingDestructor){
        const bool deleting=id==HookId::PressurePlateDeletingDestructor;
        bool& installed=deleting?pressureDeletingInstalled_:pressureDestructorInstalled_;
        if(installed)return Status{StatusCode::InvalidState};
        const auto function=deleting?0x38F2B0U:0x38F270U;
        const auto hook=deleting?0x38F2D4U:0x38F294U;
        const auto expected=deleting?0x940B82DBU:0x940B82EBU;
        const auto veneer=deleting?kPressurePlateDeletingVeneerOffset:kPressurePlateDtorVeneerOffset;
        const auto* original=deleting?pressure_plate::kDeletingOriginal.data():pressure_plate::kDestructorOriginal.data();
        const auto bytes=deleting?pressure_plate::kDeletingOriginal.size():pressure_plate::kDestructorOriginal.size();
        if(!AddressValid(target,function,bytes)||!AddressValid(target,veneer,16)||!AddressValid(target,0x66FE40,16)){
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);return Status{StatusCode::Rejected};
        }
        if(std::memcmp(engine_memory::AsObject(target.base+function),original,bytes)||
           std::memcmp(engine_memory::AsObject(target.base+0x66FE40),pressure_plate::kRngDestroyPlt.data(),16)){
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);return Status{StatusCode::Rejected};
        }
        if(s_PressureNativeBase&&s_PressureNativeBase!=target.base){
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);return Status{StatusCode::Rejected};
        }
        s_PressureNativeBase=target.base;
        s_PressureNative.destroyRng=engine_call::AsFunction<decltype(s_PressureNative.destroyRng)>(target.base+0x66FE40);
        relay::InternalHookBinding b{};b.callback=PressurePlateDestructorInternalCallback;b.user=&s_PressureNative;
        b.resumeCount=1;b.resumes[0]=target.base+hook+4;b.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
        const relay::InternalHookSite site{target.base+hook,expected};
        const auto failure=relay::TryInstallInternalHook(b,site,target.base+veneer);
        lastFailure_=static_cast<std::uint32_t>(failure);
        if(failure!=relay::InternalHookFailure::None)return Status{StatusCode::Rejected};
        installed=true;MarkPressurePlateDestructorHookInstalled(deleting);return Status::Ok();
    }
    if (id==HookId::EntityDestructorRemove) {
        if (entityDestructorInstalled_) return Status{StatusCode::InvalidState};
        if (!AddressValid(target,kEntityDestructorFunctionOffset,entity_remove::kDestructorFunction.size()) ||
            !AddressValid(target,kEntityDestructorVeneerOffset,kEntityDestructorVeneerBytes) ||
            !AddressValid(target,kEntityDestructorRngDestroyOffset,kEntityDestructorRngDestroyExpectedBytes.size())) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);
            return Status{StatusCode::Rejected};
        }
        if (std::memcmp(engine_memory::AsObject(target.base+kEntityDestructorFunctionOffset),
                        entity_remove::kDestructorFunction.data(),entity_remove::kDestructorFunction.size()) ||
            std::memcmp(engine_memory::AsObject(target.base+kEntityDestructorRngDestroyOffset),
                        kEntityDestructorRngDestroyExpectedBytes.data(),kEntityDestructorRngDestroyExpectedBytes.size())) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);
            return Status{StatusCode::Rejected};
        }
        if (s_EntityDestructorBase==0) {
            s_EntityDestructorNative.destroyRng=engine_call::AsFunction<EntityRemoveNativeBindings::RngDestroy>(
                target.base+kEntityDestructorRngDestroyOffset);
            s_EntityDestructorBase=target.base;
        } else if (s_EntityDestructorBase!=target.base) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);
            return Status{StatusCode::Rejected};
        }
        relay::InternalHookBinding binding{};
        binding.callback=EntityDestructorRemoveInternalCallback;
        binding.user=&s_EntityDestructorNative;
        binding.resumes[0]=target.base+kEntityDestructorResumeOffset;
        binding.resumeCount=1;
        binding.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
        const relay::InternalHookSite site{target.base+kEntityDestructorHookOffset,kEntityDestructorHookExpectedWord,
                                          relay::InternalVeneerKind::Literal8,target.base+kEntityDestructorPointerSlotOffset};
        const auto failure=relay::TryInstallInternalHook(binding,site,target.base+kEntityDestructorVeneerOffset);
        lastFailure_=static_cast<std::uint32_t>(failure);
        if (failure!=relay::InternalHookFailure::None) return Status{StatusCode::Rejected};
        entityDestructorInstalled_=true;
        return Status::Ok();
    }
    if (id==HookId::RoomClearAward) {
        if (clearAwardInstalled_) return Status{StatusCode::InvalidState};
        if (!AddressValid(target,0x456810,clear_award::kOriginalFunction.size()) ||
            !AddressValid(target,kClearAwardVeneerOffset,8) ||
            !AddressValid(target,kClearAwardPointerSlotOffset,8) ||
            !AddressValid(target,0x4FD0A0,12) || !AddressValid(target,0x66FCD0,16)) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);
            return Status{StatusCode::Rejected};
        }
        const std::uint8_t vectorCtor[12]={0,0,0,0xBD,1,4,0,0xBD,0xC0,3,0x5F,0xD6};
        if (std::memcmp(engine_memory::AsObject(target.base+0x456810),
                        clear_award::kOriginalFunction.data(),clear_award::kOriginalFunction.size()) ||
            std::memcmp(engine_memory::AsObject(target.base+0x4FD0A0),vectorCtor,12)) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);
            return Status{StatusCode::Rejected};
        }
        if (s_ClearAwardNativeBase==0) {
            s_ClearAwardNative.constructVector=engine_call::AsFunction<ClearAwardNativeBindings::VectorConstructor>(target.base+0x4FD0A0);
            s_ClearAwardNativeBase=target.base;
        } else if (s_ClearAwardNativeBase!=target.base) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);
            return Status{StatusCode::Rejected};
        }
        relay::InternalHookBinding binding{};
        binding.callback=ClearAwardInternalCallback;
        binding.user=&s_ClearAwardNative;
        binding.resumes[0]=target.base+kClearAwardResumeOffset;
        binding.resumes[1]=target.base+kClearAwardCleanupOffset;
        binding.resumeCount=2;
        binding.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
        const relay::InternalHookSite site{target.base+kClearAwardHookOffset,kClearAwardHookExpectedWord,
                                          relay::InternalVeneerKind::Literal8,target.base+kClearAwardPointerSlotOffset};
        const auto failure=relay::TryInstallInternalHook(binding,site,target.base+kClearAwardVeneerOffset);
        lastFailure_=static_cast<std::uint32_t>(failure);
        if (failure!=relay::InternalHookFailure::None) return Status{StatusCode::Rejected};
        clearAwardInstalled_=true;
        return Status::Ok();
    }
    if (id==HookId::ItemPoolTrinketFirstRandom || id==HookId::ItemPoolTrinketSelected) {
        const bool first = id==HookId::ItemPoolTrinketFirstRandom;
        bool& installed = first ? trinketFirstInstalled_ : trinketSelectedInstalled_;
        if (installed) return Status{StatusCode::InvalidState};
        const auto site = first ? kTrinketFirstRandomHookOffset : kTrinketSelectedHookOffset;
        const auto veneer = first ? kTrinketFirstVeneerOffset : kTrinketSelectedVeneerOffset;
        if (!AddressValid(target,site,4) || !AddressValid(target,veneer,16) ||
            target.base>UINTPTR_MAX-kTrinketManagerGotSlotOffset-sizeof(std::uintptr_t) ||
            !engine_memory::EngineMemoryReadable(target.base+kTrinketManagerGotSlotOffset,sizeof(std::uintptr_t))) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);
            return Status{StatusCode::Rejected};
        }
        if (!TrinketGuardsMatch(target,trinketFirstInstalled_,trinketSelectedInstalled_)) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);
            return Status{StatusCode::Rejected};
        }
        if (s_TrinketNativeBase==0) {
            s_TrinketNative.random=engine_call::AsFunction<TrinketNativeBindings::Random>(target.base+0x66FE30);
            s_TrinketNative.unlocked=engine_call::AsFunction<TrinketNativeBindings::Unlocked>(target.base+0x670E70);
            s_TrinketNative.managerGotSlot=target.base+kTrinketManagerGotSlotOffset;
            s_TrinketNativeBase=target.base;
        } else if (s_TrinketNativeBase!=target.base) {
            lastFailure_=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);
            return Status{StatusCode::Rejected};
        }
        relay::InternalHookBinding binding{};
        binding.callback=first ? TrinketFirstRandomInternalCallback : TrinketSelectedInternalCallback;
        binding.user=&s_TrinketNative;
        binding.resumes[0]=target.base+(first?kTrinketFirstResumeOffset:kTrinketGoldenResumeOffset);
        if (!first) binding.resumes[1]=target.base+kTrinketCleanupResumeOffset;
        binding.resumeCount=first?1U:2U;
        binding.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
        const relay::InternalHookSite hookSite{target.base+site,
            first?kTrinketFirstRandomExpectedWord:kTrinketSelectedExpectedWord};
        const auto failure=relay::TryInstallInternalHook(binding,hookSite,target.base+veneer);
        lastFailure_=static_cast<std::uint32_t>(failure);
        if (failure!=relay::InternalHookFailure::None) return Status{StatusCode::Rejected};
        installed=true;
        return Status::Ok();
    }
    if (id != HookId::RoomEntitySpawn) return Status{StatusCode::Unsupported};
    if (installed_) return Status{StatusCode::InvalidState};
    if (!AddressValid(target, 0x452984, 4) || !AddressValid(target,0x68CFD0,16) ||
        target.base > UINTPTR_MAX-0xAAC698-sizeof(std::uintptr_t) ||
        !engine_memory::EngineMemoryReadable(target.base+0xAAC698,sizeof(std::uintptr_t))) {
        lastFailure_ = static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);
        return Status{StatusCode::Rejected};
    }
    for (const auto& guard : kGuards) {
        if (!AddressValid(target,guard.offset,guard.bytes.size()) ||
            std::memcmp(engine_memory::AsObject(target.base+guard.offset),guard.bytes.data(),guard.bytes.size()) != 0) {
            lastFailure_ = static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);
            return Status{StatusCode::Rejected};
        }
    }
    if (std::memcmp(engine_memory::AsObject(target.base+0x4529C8),kNormal.data(),kNormal.size()) != 0 ||
        std::memcmp(engine_memory::AsObject(target.base+0x452AA8),kSpecial.data(),kSpecial.size()) != 0) {
        lastFailure_ = static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);
        return Status{StatusCode::Rejected};
    }
    s_Native.next = engine_call::AsFunction<RoomSpawnNativeBindings::Next>(target.base+0x66FE90);
    s_Native.getCard = engine_call::AsFunction<RoomSpawnNativeBindings::GetCard>(target.base+0x6743B0);
    s_Native.construct = engine_call::AsFunction<RoomSpawnNativeBindings::Construct>(target.base+0x66FE20);
    s_Native.random = engine_call::AsFunction<RoomSpawnNativeBindings::Random>(target.base+0x66FE30);
    s_Native.gameGotSlot = target.base+0xAAC698;
    relay::InternalHookBinding binding{};
    binding.callback = RoomFixSpawnCtorInternalCallback;
    binding.user = &s_Native;
    binding.resumes[0] = target.base+0x452A1C;
    binding.resumes[1] = target.base+0x453798;
    binding.resumeCount = 2;
    binding.scratch = relay::InternalScratchPolicy::ProvedDeadX16;
    const relay::InternalHookSite site{target.base+0x452984,0x94087527U};
    const auto failure = relay::TryInstallInternalHook(binding,site,target.base+kRoomSpawnInternalVeneerOffset);
    lastFailure_ = static_cast<std::uint32_t>(failure);
    if (failure != relay::InternalHookFailure::None) return Status{StatusCode::Rejected};
    installed_ = true;
    return Status::Ok();
}
bool InternalHookAdapter::IsInstalled(HookId id) const noexcept {
    if(id==HookId::PressurePlateDestructor)return pressureDestructorInstalled_;
    if(id==HookId::PressurePlateDeletingDestructor)return pressureDeletingInstalled_;
    if(id==HookId::ConsoleUnknownLength)return consoleLengthInstalled_;
    if(id==HookId::ConsoleUnknownCompare)return consoleCompareInstalled_;
    if (id==HookId::EntityDestructorRemove) return entityDestructorInstalled_;
    if (id==HookId::LevelCurseFirstRandom) return levelCurseFirstInstalled_;
    if (id==HookId::LevelCurseEvaluation) return levelCurseEvaluationInstalled_;
    if (id==HookId::PickupSelection) return pickupSelectionInstalled_;
    if (id==HookId::PickupSelectionSpecial) return pickupSelectionSpecialInstalled_;
    if (id==HookId::RoomClearAward) return clearAwardInstalled_;
    if (id==HookId::ItemPoolTrinketFirstRandom) return trinketFirstInstalled_;
    if (id==HookId::ItemPoolTrinketSelected) return trinketSelectedInstalled_;
    return id == HookId::RoomEntitySpawn && installed_;
}
} // namespace isaac::runtime
