#pragma once

// Portable REPENTOGON console completion data and pinned LANG fallbacks.
// Derived from TeamREPENTOGON ConsoleMega.h and Localization/*.inl at pinned
// commit 03e04726f37aa0f5be4e438e5296fd70e7abbd4a (GPL-2.0).
// Grid/Debug/Combo/command strings are generated from the pinned
// Localization/*.inl files; missing translations fall back to en_us.inl.
// Runtime XML/StringTable data arrives through the private completion provider.

#include "domain/console/console_commands.hpp"
#include "ports/console_autocomplete_port.hpp"

#include <cstddef>
#include <cstdint>
#include <iterator>

namespace isaac::runtime::console {

struct ConsoleLocalizedText {
    const char* values[8];

    [[nodiscard]] const char* Select(std::uint32_t language) const noexcept {
        switch (language) {
            case 2: return values[1];
            case 3: return values[2];
            case 4: return values[3];
            case 5: return values[4];
            case 10: return values[5];
            case 11: return values[6];
            case 13: return values[7];
            default: return values[0];
        }
    }
};

using ConsoleCatalogLanguageProvider = std::uint32_t (*)() noexcept;

inline ConsoleCatalogLanguageProvider& ConsoleCatalogLanguageSlot() noexcept {
    static ConsoleCatalogLanguageProvider provider{};
    return provider;
}

inline void SetConsoleCatalogLanguageProvider(ConsoleCatalogLanguageProvider provider) noexcept {
    ConsoleCatalogLanguageSlot() = provider;
}

[[nodiscard]] inline std::uint32_t ConsoleCatalogLanguage() noexcept {
    const auto provider = ConsoleCatalogLanguageSlot();
    return provider != nullptr ? provider() : 0U;
}

struct ConsoleCompletionCatalogEntry {
    const char* text;
    const char* description;
    const ConsoleLocalizedText* localizedDescription;
};

struct ConsoleStageCompletionRule {
    const char* text;
    const char* description;
    const char* nameKey;
    const char* postfix;
    const ConsoleLocalizedText* localizedDescription;
};

struct ConsoleBuiltinCommandMetadata {
    const char* name;
    const char* alias;
    const char* description;
    const char* helpText;
    const ConsoleLocalizedText* localizedDescription;
    const ConsoleLocalizedText* localizedHelpText;
    bool showOnMenu;
    ConsoleAutocompleteType autocompleteType;
};

inline constexpr ConsoleLocalizedText kConsoleStageLocalizedDescriptions[] = {
    {{"\?\?\? / Blue Womb", "\?\?\? / Blue Womb", "\?\?\? / Blue Womb", "\?\?\? / Vientre Azul", "\?\?\? / Blue Womb", "\?\?\? / Blue Womb", "\?\?\? / 푸른 자궁", "\?\?\?/蓝子宫"}},
    {{"Home (day)", "Home (day)", "Home (day)", "Hogar (dia)", "Home (day)", "Home (day)", "집 (낮)", "家（白天）"}},
    {{"Home (night)", "Home (night)", "Home (night)", "Hogar (noche)", "Home (night)", "Home (night)", "집 (밤)", "家（夜晚）"}},
};

inline constexpr ConsoleLocalizedText kConsoleCompletionGridLocalizedDescriptions[] = {
    {{"Decoration A", "Decoration A", "Decoration A", "Decoracion A", "Decoration A", "Decoration A", "Decoration A 치장성 타일 A", "Decoration A 地面装饰 A"}},
    {{"Decoration B", "Decoration B", "Decoration B", "Decoracion B", "Decoration B", "Decoration B", "Decoration B 치장성 타일 B", "Decoration B 地面装饰 B"}},
    {{"Decoration C", "Decoration C", "Decoration C", "Decoracion C", "Decoration C", "Decoration C", "Decoration C 치장성 타일 C", "Decoration C 地面装饰 C"}},
    {{"Rock", "Rock", "Rock", "Roca", "Rock", "Rock", "Rock 돌", "Rock 石头"}},
    {{"Rock (connecting)", "Rock (connecting)", "Rock (connecting)", "Roca (conectada)", "Rock (connecting)", "Rock (connecting)", "Rock (connecting) 돌 (연결)", "Rock (connecting) 石头 (过渡)"}},
    {{"Bomb Rock", "Bomb Rock", "Bomb Rock", "Roca Explosiva", "Bomb Rock", "Bomb Rock", "Bomb Rock 폭탄 돌", "Bomb Rock 炸弹石头"}},
    {{"Alt Rock", "Alt Rock", "Alt Rock", "Roca Alterna", "Alt Rock", "Alt Rock", "Alt Rock 특수 돌", "Alt Rock 特殊石头"}},
    {{"Tinted Rock", "Tinted Rock", "Tinted Rock", "Roca Marcada", "Tinted Rock", "Tinted Rock", "Tinted Rock 색돌", "Tinted Rock 标记石头"}},
    {{"Marked Skull", "Marked Skull", "Marked Skull", "Craneo Marcado", "Marked Skull", "Marked Skull", "Marked Skull 표식 해골", "Marked Skull 标记头骨"}},
    {{"Event Rock", "Event Rock", "Event Rock", "Roca de Evento", "Event Rock", "Event Rock", "Event Rock 이벤트 돌", "Event Rock 事件石头"}},
    {{"Spiked Rock", "Spiked Rock", "Spiked Rock", "Roca con Espinas", "Spiked Rock", "Spiked Rock", "Spiked Rock 색돌", "Spiked Rock 刺石头"}},
    {{"Fool's Gold Rock", "Fool's Gold Rock", "Fool's Gold Rock", "Roca Dorada", "Fool's Gold Rock", "Fool's Gold Rock", "Fool's Gold Rock 바보의 황금 돌", "Fool's Gold Rock 愚人金石头"}},
    {{"TNT", "TNT", "TNT", "TNT", "TNT", "TNT", "TNT TNT", "TNT 炸药桶"}},
    {{"Fire Place", "Fire Place", "Fire Place", "Fogata", "Fire Place", "Fire Place", "Fire Place 모닥불", "Fire Place 火堆"}},
    {{"Red Fire Place", "Red Fire Place", "Red Fire Place", "Fogata Roja", "Red Fire Place", "Red Fire Place", "Red Fire Place 빨간 모닥불", "Red Fire Place 红色火堆"}},
    {{"Red Poop", "Red Poop", "Red Poop", "Caca Roja", "Red Poop", "Red Poop", "Red Poop 빨간 응아", "Red Poop 红大便"}},
    {{"Rainbow Poop", "Rainbow Poop", "Rainbow Poop", "Caca Arcoiris", "Rainbow Poop", "Rainbow Poop", "Rainbow Poop 무지개 응아", "Rainbow Poop 彩虹大便"}},
    {{"Corny Poop", "Corny Poop", "Corny Poop", "Caca Corny", "Corny Poop", "Corny Poop", "Corny Poop 옥수수 응아", "Corny Poop 玉米大便"}},
    {{"Golden Poop", "Golden Poop", "Golden Poop", "Caca Dorada", "Golden Poop", "Golden Poop", "Golden Poop 황금 응아", "Golden Poop 金大便"}},
    {{"Black Poop", "Black Poop", "Black Poop", "Caca Negra", "Black Poop", "Black Poop", "Black Poop 검은 응아", "Black Poop 黑大便"}},
    {{"White Poop", "White Poop", "White Poop", "Caca Blanca", "White Poop", "White Poop", "White Poop 하얀 응아", "White Poop 白大便"}},
    {{"Giant Poop", "Giant Poop", "Giant Poop", "Caca Gigante", "Giant Poop", "Giant Poop", "Giant Poop 거대 응아", "Giant Poop 巨型大便"}},
    {{"Poop", "Poop", "Poop", "Caca", "Poop", "Poop", "Poop 응아", "Poop 大便"}},
    {{"Charming Poop", "Charming Poop", "Charming Poop", "Caca Encantadora", "Charming Poop", "Charming Poop", "Charming Poop 예쁜 응아", "Charming Poop 友好大便"}},
    {{"Block", "Block", "Block", "Bloque", "Block", "Block", "Block 블록", "Block 方块"}},
    {{"Pillar", "Pillar", "Pillar", "Pilar", "Pillar", "Pillar", "Pillar 기둥", "Pillar 柱子"}},
    {{"Spikes", "Spikes", "Spikes", "Espinas", "Spikes", "Spikes", "Spikes 가시", "Spikes 地刺"}},
    {{"Sanguine Bond Spikes", "Sanguine Bond Spikes", "Sanguine Bond Spikes", "Espinas de Vinculo de Sangre", "Sanguine Bond Spikes", "Sanguine Bond Spikes", "Sanguine Bond Spikes 피의 결속 가시", "Sanguine Bond Spikes 血色羁绊尖刺"}},
    {{"Retractable Spikes", "Retractable Spikes", "Retractable Spikes", "Espinas Retraibles", "Retractable Spikes", "Retractable Spikes", "Retractable Spikes 개폐식 가시", "Retractable Spikes 伸缩地刺"}},
    {{"Retractable Spikes (down 1/5)", "Retractable Spikes (down 1/5)", "Retractable Spikes (down 1/5)", "Espinas Retraibles (abajo 1/5)", "Retractable Spikes (down 1/5)", "Retractable Spikes (down 1/5)", "Retractable Spikes (down 1/5) 개폐식 가시 (1/5 하강)", "Retractable Spikes (down 1/5) 伸缩地刺 (缩1/5)"}},
    {{"Retractable Spikes (down 2/5)", "Retractable Spikes (down 2/5)", "Retractable Spikes (down 2/5)", "Espinas Retraibles (abajo 2/5)", "Retractable Spikes (down 2/5)", "Retractable Spikes (down 2/5)", "Retractable Spikes (down 2/5) 개폐식 가시 (2/5 하강)", "Retractable Spikes (down 2/5) 伸缩地刺 (缩2/5)"}},
    {{"Retractable Spikes (down 3/5)", "Retractable Spikes (down 3/5)", "Retractable Spikes (down 3/5)", "Espinas Retraibles (abajo 3/5)", "Retractable Spikes (down 3/5)", "Retractable Spikes (down 3/5)", "Retractable Spikes (down 3/5) 개폐식 가시 (3/5 하강)", "Retractable Spikes (down 3/5) 伸缩地刺 (缩3/5)"}},
    {{"Retractable Spikes (down 4/5)", "Retractable Spikes (down 4/5)", "Retractable Spikes (down 4/5)", "Espinas Retraibles (abajo 4/5)", "Retractable Spikes (down 4/5)", "Retractable Spikes (down 4/5)", "Retractable Spikes (down 4/5) 개폐식 가시 (4/5 하강)", "Retractable Spikes (down 4/5) 伸缩地刺 (缩4/5)"}},
    {{"Retractable Spikes (down 5/5)", "Retractable Spikes (down 5/5)", "Retractable Spikes (down 5/5)", "Espinas Retraibles (abajo 5/5)", "Retractable Spikes (down 5/5)", "Retractable Spikes (down 5/5)", "Retractable Spikes (down 5/5) 개폐식 가시 (5/5 하강)", "Retractable Spikes (down 5/5) 伸缩地刺 (缩5/5)"}},
    {{"Retractable Spikes (up 1/5)", "Retractable Spikes (up 1/5)", "Retractable Spikes (up 1/5)", "Espinas Retraibles (arriba 1/5)", "Retractable Spikes (up 1/5)", "Retractable Spikes (up 1/5)", "Retractable Spikes (up 1/5) 개폐식 가시 (1/5 상승)", "Retractable Spikes (up 1/5) 伸缩地刺 (伸1/5)"}},
    {{"Retractable Spikes (up 2/5)", "Retractable Spikes (up 2/5)", "Retractable Spikes (up 2/5)", "Espinas Retraibles (arriba 2/5)", "Retractable Spikes (up 2/5)", "Retractable Spikes (up 2/5)", "Retractable Spikes (up 2/5) 개폐식 가시 (2/5 상승)", "Retractable Spikes (up 2/5) 伸缩地刺 (伸2/5)"}},
    {{"Retractable Spikes (up 3/5)", "Retractable Spikes (up 3/5)", "Retractable Spikes (up 3/5)", "Espinas Retraibles (arriba 3/5)", "Retractable Spikes (up 3/5)", "Retractable Spikes (up 3/5)", "Retractable Spikes (up 3/5) 개폐식 가시 (3/5 상승)", "Retractable Spikes (up 3/5) 伸缩地刺 (伸3/5)"}},
    {{"Retractable Spikes (up 4/5)", "Retractable Spikes (up 4/5)", "Retractable Spikes (up 4/5)", "Espinas Retraibles (arriba 4/5)", "Retractable Spikes (up 4/5)", "Retractable Spikes (up 4/5)", "Retractable Spikes (up 4/5) 개폐식 가시 (4/5 상승)", "Retractable Spikes (up 4/5) 伸缩地刺 (伸4/5)"}},
    {{"Retractable Spikes (up 5/5)", "Retractable Spikes (up 5/5)", "Retractable Spikes (up 5/5)", "Espinas Retraibles (arriba 5/5)", "Retractable Spikes (up 5/5)", "Retractable Spikes (up 5/5)", "Retractable Spikes (up 5/5) 개폐식 가시 (5/5 상승)", "Retractable Spikes (up 5/5) 伸缩地刺 (伸5/5)"}},
    {{"Cobweb", "Cobweb", "Cobweb", "Telaraña", "Cobweb", "Cobweb", "Cobweb 거미줄", "Cobweb 蛛网"}},
    {{"Invisible Block", "Invisible Block", "Invisible Block", "Bloque Invisible", "Invisible Block", "Invisible Block", "Invisible Block 투명 블록", "Invisible Block 隐形方块"}},
    {{"Pit", "Pit", "Pit", "Pozo", "Pit", "Pit", "Pit 구멍", "Pit 沟壑"}},
    {{"Fissure Spawner", "Fissure Spawner", "Fissure Spawner", "Generador de Fissure", "Fissure Spawner", "Fissure Spawner", "Fissure Spawner 피셔 생성기", "Fissure Spawner 骷髅鱼生成器"}},
    {{"Event Rail", "Event Rail", "Event Rail", "Riel de Evento", "Event Rail", "Event Rail", "Event Rail 이벤트 레일", "Event Rail 事件铁轨"}},
    {{"Event Pit", "Event Pit", "Event Pit", "Pozo de Evento", "Event Pit", "Event Pit", "Event Pit 이벤트 구멍", "Event Pit 事件沟壑"}},
    {{"Key Block", "Key Block", "Key Block", "Bloque Cerrado", "Key Block", "Key Block", "Key Block 열쇠 블록", "Key Block 钥匙方块"}},
    {{"Pressure Plate", "Pressure Plate", "Pressure Plate", "Placa de Presion", "Pressure Plate", "Pressure Plate", "Pressure Plate 압력판", "Pressure Plate 银按钮"}},
    {{"Reward Plate", "Reward Plate", "Reward Plate", "Placa de Recompensa", "Reward Plate", "Reward Plate", "Reward Plate 보상 압력판", "Reward Plate 奖励按钮"}},
    {{"Greed Plate", "Greed Plate", "Greed Plate", "Placa de Greed", "Greed Plate", "Greed Plate", "Greed Plate 탐욕 압력판", "Greed Plate 贪婪按钮"}},
    {{"Rail Plate", "Rail Plate", "Rail Plate", "Placa de Riel", "Rail Plate", "Rail Plate", "Rail Plate 레일 압력판", "Rail Plate 铁轨按钮"}},
    {{"Kill Plate", "Kill Plate", "Kill Plate", "Placa de Muerte", "Kill Plate", "Kill Plate", "Kill Plate 즉사 압력판", "Kill Plate 击杀按钮"}},
    {{"Event Plate (group 0)", "Event Plate (group 0)", "Event Plate (group 0)", "Placa de Evento (grupo 0)", "Event Plate (group 0)", "Event Plate (group 0)", "Event Plate (group 0) 이벤트 압력판 (그룹 0)", "Event Plate (group 0) 事件按钮 (组0)"}},
    {{"Event Plate (group 1)", "Event Plate (group 1)", "Event Plate (group 1)", "Placa de Evento (grupo 1)", "Event Plate (group 1)", "Event Plate (group 1)", "Event Plate (group 1) 이벤트 압력판 (그룹 1)", "Event Plate (group 1) 事件按钮 (组1)"}},
    {{"Event Plate (group 2)", "Event Plate (group 2)", "Event Plate (group 2)", "Placa de Evento (grupo 2)", "Event Plate (group 2)", "Event Plate (group 2)", "Event Plate (group 2) 이벤트 압력판 (그룹 2)", "Event Plate (group 2) 事件按钮 (组2)"}},
    {{"Event Plate (group 3)", "Event Plate (group 3)", "Event Plate (group 3)", "Placa de Evento (grupo 3)", "Event Plate (group 3)", "Event Plate (group 3)", "Event Plate (group 3) 이벤트 압력판 (그룹 3)", "Event Plate (group 3) 事件按钮 (组3)"}},
    {{"Devil Statue", "Devil Statue", "Devil Statue", "Estatua de Diablo", "Devil Statue", "Devil Statue", "Devil Statue 악마 석상", "Devil Statue 恶魔雕像"}},
    {{"Angel Statue", "Angel Statue", "Angel Statue", "Estatua de Ángel", "Angel Statue", "Angel Statue", "Angel Statue 천사 석상", "Angel Statue 天使雕像"}},
    {{"Rail (horizontal)", "Rail (horizontal)", "Rail (horizontal)", "Riel (horizontal)", "Rail (horizontal)", "Rail (horizontal)", "Rail (horizontal) 레일 (가로)", "Rail (horizontal) 铁轨(横向)"}},
    {{"Rail (vertical)", "Rail (vertical)", "Rail (vertical)", "Riel (vertical)", "Rail (vertical)", "Rail (vertical)", "Rail (vertical) 레일 (세로)", "Rail (vertical) 铁轨(纵向)"}},
    {{"Rail (down-to-right)", "Rail (down-to-right)", "Rail (down-to-right)", "Riel (abajo-a-derecha)", "Rail (down-to-right)", "Rail (down-to-right)", "Rail (down-to-right) 레일 (우-하)", "Rail (down-to-right) 铁轨(下-右)"}},
    {{"Rail (down-to-left)", "Rail (down-to-left)", "Rail (down-to-left)", "Riel (abajo-a-izquierda)", "Rail (down-to-left)", "Rail (down-to-left)", "Rail (down-to-left) 레일 (좌-하)", "Rail (down-to-left) 铁轨(下-左)"}},
    {{"Rail (up-to-right)", "Rail (up-to-right)", "Rail (up-to-right)", "Riel (arriba-a-derecha)", "Rail (up-to-right)", "Rail (up-to-right)", "Rail (up-to-right) 레일 (우-상)", "Rail (up-to-right) 铁轨(上-右)"}},
    {{"Rail (up-to-left)", "Rail (up-to-left)", "Rail (up-to-left)", "Riel (arriba-a-izquierda)", "Rail (up-to-left)", "Rail (up-to-left)", "Rail (up-to-left) 레일 (좌-상)", "Rail (up-to-left) 铁轨(上-左)"}},
    {{"Rail (crossroad)", "Rail (crossroad)", "Rail (crossroad)", "Riel (cruce)", "Rail (crossroad)", "Rail (crossroad)", "Rail (crossroad) 레일 (교차)", "Rail (crossroad) 铁轨(十字)"}},
    {{"Rail (end-left)", "Rail (end-left)", "Rail (end-left)", "Riel (final-izquierda)", "Rail (end-left)", "Rail (end-left)", "Rail (end-left) 레일 (좌측 끝)", "Rail (end-left) 铁轨(左终止)"}},
    {{"Rail (end-right)", "Rail (end-right)", "Rail (end-right)", "Riel (final-derecha)", "Rail (end-right)", "Rail (end-right)", "Rail (end-right) 레일 (우측 끝)", "Rail (end-right) 铁轨(右终止)"}},
    {{"Rail (end-up)", "Rail (end-up)", "Rail (end-up)", "Riel (final-arriba)", "Rail (end-up)", "Rail (end-up)", "Rail (end-up) 레일 (상단 끝)", "Rail (end-up) 铁轨(上终止)"}},
    {{"Rail (end-down)", "Rail (end-down)", "Rail (end-down)", "Riel (final-abajo)", "Rail (end-down)", "Rail (end-down)", "Rail (end-down) 레일 (하단 끝)", "Rail (end-down) 铁轨(下终止)"}},
    {{"Rail (cart-left)", "Rail (cart-left)", "Rail (cart-left)", "Riel (carrito-izquierda)", "Rail (cart-left)", "Rail (cart-left)", "Rail (cart-left) 레일 (좌-카트)", "Rail (cart-left) 铁轨(左开放)"}},
    {{"Rail (cart-up)", "Rail (cart-up)", "Rail (cart-up)", "Riel (carrito-arriba)", "Rail (cart-up)", "Rail (cart-up)", "Rail (cart-up) 레일 (상-카트)", "Rail (cart-up) 铁轨(上开放)"}},
    {{"Rail (cart-right)", "Rail (cart-right)", "Rail (cart-right)", "Riel (carrito-derecha)", "Rail (cart-right)", "Rail (cart-right)", "Rail (cart-right) 레일 (우-카트)", "Rail (cart-right) 铁轨(右开放)"}},
    {{"Rail (cart-down)", "Rail (cart-down)", "Rail (cart-down)", "Riel (carrito-abajo)", "Rail (cart-down)", "Rail (cart-down)", "Rail (cart-down) 레일 (하-카트)", "Rail (cart-down) 铁轨(下开放)"}},
    {{"Mineshaft Rail (horizontal 1)", "Mineshaft Rail (horizontal 1)", "Mineshaft Rail (horizontal 1)", "Riel de Mina (horizontal 1)", "Mineshaft Rail (horizontal 1)", "Mineshaft Rail (horizontal 1)", "Mineshaft Rail (horizontal 1) 폐광 레일 (가로 1)", "Mineshaft Rail (horizontal 1) 矿洞铁轨 (横向 1)"}},
    {{"Mineshaft Rail (vertical 1)", "Mineshaft Rail (vertical 1)", "Mineshaft Rail (vertical 1)", "Riel de Mina (vertical 1)", "Mineshaft Rail (vertical 1)", "Mineshaft Rail (vertical 1)", "Mineshaft Rail (vertical 1) 폐광 레일 (세로 1)", "Mineshaft Rail (vertical 1) 矿洞铁轨 (纵向 1)"}},
    {{"Mineshaft Rail (down-to-right 1)", "Mineshaft Rail (down-to-right 1)", "Mineshaft Rail (down-to-right 1)", "Riel de Mina (abajo-a-derecha 1)", "Mineshaft Rail (down-to-right 1)", "Mineshaft Rail (down-to-right 1)", "Mineshaft Rail (down-to-right 1) 폐광 레일 (우-하 1)", "Mineshaft Rail (down-to-right 1) 矿洞铁轨 (下-右 1)"}},
    {{"Mineshaft Rail (down-to-left 1)", "Mineshaft Rail (down-to-left 1)", "Mineshaft Rail (down-to-left 1)", "Riel de Mina (abajo-a-izquierda 1)", "Mineshaft Rail (down-to-left 1)", "Mineshaft Rail (down-to-left 1)", "Mineshaft Rail (down-to-left 1) 폐광 레일 (좌-하 1)", "Mineshaft Rail (down-to-left 1) 矿洞铁轨 (下-左 1)"}},
    {{"Mineshaft Rail (up-to-right 1)", "Mineshaft Rail (up-to-right 1)", "Mineshaft Rail (up-to-right 1)", "Riel de Mina (arriba-a-derecha 1)", "Mineshaft Rail (up-to-right 1)", "Mineshaft Rail (up-to-right 1)", "Mineshaft Rail (up-to-right 1) 폐광 레일 (우-상 1)", "Mineshaft Rail (up-to-right 1) 矿洞铁轨 (上-右 1)"}},
    {{"Mineshaft Rail (up-to-left 1)", "Mineshaft Rail (up-to-left 1)", "Mineshaft Rail (up-to-left 1)", "Riel de Mina (arriba-a-izquierda 1)", "Mineshaft Rail (up-to-left 1)", "Mineshaft Rail (up-to-left 1)", "Mineshaft Rail (up-to-left 1) 폐광 레일 (좌-상 1)", "Mineshaft Rail (up-to-left 1) 矿洞铁轨 (上-左 1)"}},
    {{"Mineshaft Rail (horizontal 2)", "Mineshaft Rail (horizontal 2)", "Mineshaft Rail (horizontal 2)", "Riel de Mina (horizontal 2)", "Mineshaft Rail (horizontal 2)", "Mineshaft Rail (horizontal 2)", "Mineshaft Rail (horizontal 2) 폐광 레일 (가로 2)", "Mineshaft Rail (horizontal 2) 矿洞铁轨 (横向 2)"}},
    {{"Mineshaft Rail (vertical 2)", "Mineshaft Rail (vertical 2)", "Mineshaft Rail (vertical 2)", "Riel de Mina (vertical 2)", "Mineshaft Rail (vertical 2)", "Mineshaft Rail (vertical 2)", "Mineshaft Rail (vertical 2) 폐광 레일 (세로 2)", "Mineshaft Rail (vertical 2) 矿洞铁轨 (纵向 2)"}},
    {{"Mineshaft Rail (down-to-right 2)", "Mineshaft Rail (down-to-right 2)", "Mineshaft Rail (down-to-right 2)", "Riel de Mina (abajo-a-derecha 2)", "Mineshaft Rail (down-to-right 2)", "Mineshaft Rail (down-to-right 2)", "Mineshaft Rail (down-to-right 2) 폐광 레일 (우-하 2)", "Mineshaft Rail (down-to-right 2) 矿洞铁轨 (下-右 2)"}},
    {{"Mineshaft Rail (down-to-left 2)", "Mineshaft Rail (down-to-left 2)", "Mineshaft Rail (down-to-left 2)", "Riel de Mina (abajo-a-izquierda 2)", "Mineshaft Rail (down-to-left 2)", "Mineshaft Rail (down-to-left 2)", "Mineshaft Rail (down-to-left 2) 폐광 레일 (좌-하 2)", "Mineshaft Rail (down-to-left 2) 矿洞铁轨 (下-左 2)"}},
    {{"Mineshaft Rail (up-to-right 2)", "Mineshaft Rail (up-to-right 2)", "Mineshaft Rail (up-to-right 2)", "Riel de Mina (arriba-a-derecha 2)", "Mineshaft Rail (up-to-right 2)", "Mineshaft Rail (up-to-right 2)", "Mineshaft Rail (up-to-right 2) 폐광 레일 (우-상 2)", "Mineshaft Rail (up-to-right 2) 矿洞铁轨 (上-右 2)"}},
    {{"Mineshaft Rail (up-to-left 2)", "Mineshaft Rail (up-to-left 2)", "Mineshaft Rail (up-to-left 2)", "Riel de Mina (arriba-a-izquierda 2)", "Mineshaft Rail (up-to-left 2)", "Mineshaft Rail (up-to-left 2)", "Mineshaft Rail (up-to-left 2) 폐광 레일 (좌-상 2)", "Mineshaft Rail (up-to-left 2) 矿洞铁轨 (上-左 2)"}},
    {{"Mineshaft Rail (horizontal 3)", "Mineshaft Rail (horizontal 3)", "Mineshaft Rail (horizontal 3)", "Riel de Mina (horizontal 3)", "Mineshaft Rail (horizontal 3)", "Mineshaft Rail (horizontal 3)", "Mineshaft Rail (horizontal 3) 폐광 레일 (가로 3)", "Mineshaft Rail (horizontal 3) 矿洞铁轨 (横向 3)"}},
    {{"Mineshaft Rail (vertical 3)", "Mineshaft Rail (vertical 3)", "Mineshaft Rail (vertical 3)", "Riel de Mina (vertical 3)", "Mineshaft Rail (vertical 3)", "Mineshaft Rail (vertical 3)", "Mineshaft Rail (vertical 3) 폐광 레일 (세로 3)", "Mineshaft Rail (vertical 3) 矿洞铁轨 (纵向 3)"}},
    {{"Rail Pit (horizontal)", "Rail Pit (horizontal)", "Rail Pit (horizontal)", "Pozo de Riel (horizontal)", "Rail Pit (horizontal)", "Rail Pit (horizontal)", "Rail Pit (horizontal) 레일 구덩이 (가로)", "Rail Pit (horizontal) 沟壑铁轨(横向)"}},
    {{"Rail Pit (vertical)", "Rail Pit (vertical)", "Rail Pit (vertical)", "Pozo de Riel (vertical)", "Rail Pit (vertical)", "Rail Pit (vertical)", "Rail Pit (vertical) 레일 구덩이 (세로)", "Rail Pit (vertical) 沟壑铁轨(纵向)"}},
    {{"Rail Pit (down-to-right)", "Rail Pit (down-to-right)", "Rail Pit (down-to-right)", "Pozo de Riel (abajo-a-derecha)", "Rail Pit (down-to-right)", "Rail Pit (down-to-right)", "Rail Pit (down-to-right) 레일 구덩이 (우-하)", "Rail Pit (down-to-right) 沟壑铁轨(下-右)"}},
    {{"Rail Pit (down-to-left)", "Rail Pit (down-to-left)", "Rail Pit (down-to-left)", "Pozo de Riel (abajo-a-izquierda)", "Rail Pit (down-to-left)", "Rail Pit (down-to-left)", "Rail Pit (down-to-left) 레일 구덩이 (좌-하)", "Rail Pit (down-to-left) 沟壑铁轨(下-左)"}},
    {{"Rail Pit (up-to-right)", "Rail Pit (up-to-right)", "Rail Pit (up-to-right)", "Pozo de Riel (arriba-a-derecha)", "Rail Pit (up-to-right)", "Rail Pit (up-to-right)", "Rail Pit (up-to-right) 레일 구덩이 (우-상)", "Rail Pit (up-to-right) 沟壑铁轨(上-右)"}},
    {{"Rail Pit (up-to-left)", "Rail Pit (up-to-left)", "Rail Pit (up-to-left)", "Pozo de Riel (arriba-a-izquierda)", "Rail Pit (up-to-left)", "Rail Pit (up-to-left)", "Rail Pit (up-to-left) 레일 구덩이 (좌-상)", "Rail Pit (up-to-left) 沟壑铁轨(上-左)"}},
    {{"Rail Pit (crossroad)", "Rail Pit (crossroad)", "Rail Pit (crossroad)", "Pozo de Riel (cruce)", "Rail Pit (crossroad)", "Rail Pit (crossroad)", "Rail Pit (crossroad) 레일 구덩이 (교차)", "Rail Pit (crossroad) 沟壑铁轨(交叉)"}},
    {{"Rail Pit (cart-left)", "Rail Pit (cart-left)", "Rail Pit (cart-left)", "Pozo de Riel (carrito-izquierda)", "Rail Pit (cart-left)", "Rail Pit (cart-left)", "Rail Pit (cart-left) 레일 구덩이 (좌-카트)", "Rail Pit (cart-left) 沟壑铁轨(左开放)"}},
    {{"Rail Pit (cart-up)", "Rail Pit (cart-up)", "Rail Pit (cart-up)", "Pozo de Riel (carrito-arriba)", "Rail Pit (cart-up)", "Rail Pit (cart-up)", "Rail Pit (cart-up) 레일 구덩이 (상-카트)", "Rail Pit (cart-up) 沟壑铁轨(上开放)"}},
    {{"Rail Pit (cart-right)", "Rail Pit (cart-right)", "Rail Pit (cart-right)", "Pozo de Riel (carrito-derecha)", "Rail Pit (cart-right)", "Rail Pit (cart-right)", "Rail Pit (cart-right) 레일 구덩이 (우-카트)", "Rail Pit (cart-right) 沟壑铁轨(右开放)"}},
    {{"Rail Pit (cart-down)", "Rail Pit (cart-down)", "Rail Pit (cart-down)", "Pozo de Riel (carrito-abajo)", "Rail Pit (cart-down)", "Rail Pit (cart-down)", "Rail Pit (cart-down) 레일 구덩이 (하-카트)", "Rail Pit (cart-down) 沟壑铁轨(下开放)"}},
    {{"Teleporter (square)", "Teleporter (square)", "Teleporter (square)", "Teleportador (cuadrado)", "Teleporter (square)", "Teleporter (square)", "Teleporter (square) 순간이동기 (네모)", "Teleporter (square) 传送点(方)"}},
    {{"Teleporter (moon)", "Teleporter (moon)", "Teleporter (moon)", "Teleportador (luna)", "Teleporter (moon)", "Teleporter (moon)", "Teleporter (moon) 순간이동기 (달)", "Teleporter (moon) 传送点(月)"}},
    {{"Teleporter (rhombus)", "Teleporter (rhombus)", "Teleporter (rhombus)", "Teleportador (rombo)", "Teleporter (rhombus)", "Teleporter (rhombus)", "Teleporter (rhombus) 순간이동기 (마름모)", "Teleporter (rhombus) 传送点(菱)"}},
    {{"Teleporter (M)", "Teleporter (M)", "Teleporter (M)", "Teleportador (M)", "Teleporter (M)", "Teleporter (M)", "Teleporter (M) 순간이동기 (M)", "Teleporter (M) 传送点(M)"}},
    {{"Teleporter (pentagram)", "Teleporter (pentagram)", "Teleporter (pentagram)", "Teleportador (pentagrama)", "Teleporter (pentagram)", "Teleporter (pentagram)", "Teleporter (pentagram) 순간이동기 (오망성)", "Teleporter (pentagram) 传送点(五角星)"}},
    {{"Teleporter (cross)", "Teleporter (cross)", "Teleporter (cross)", "Teleportador (cruz)", "Teleporter (cross)", "Teleporter (cross)", "Teleporter (cross) 순간이동기 (십자가)", "Teleporter (cross) 传送点(十)"}},
    {{"Teleporter (triangle)", "Teleporter (triangle)", "Teleporter (triangle)", "Teleportador (triangulo)", "Teleporter (triangle)", "Teleporter (triangle)", "Teleporter (triangle) 순간이동기 (삼각형)", "Teleporter (triangle) 传送点(三角)"}},
    {{"Trap Door", "Trap Door", "Trap Door", "Trampilla", "Trap Door", "Trap Door", "Trap Door 순간이동기 (다락문)", "Trap Door 活板门"}},
    {{"Void Portal", "Void Portal", "Void Portal", "Portal de Vacío", "Void Portal", "Void Portal", "Void Portal 순간이동기 (공허 포탈)", "Void Portal 虚空传送门"}},
    {{"Crawlspace", "Crawlspace", "Crawlspace", "Mazmorra", "Crawlspace", "Crawlspace", "Crawlspace 사다리방", "Crawlspace 暗门"}},
    {{"Crawlspace (Gideon dungeon)", "Crawlspace (Gideon dungeon)", "Crawlspace (Gideon dungeon)", "Mazmorra (calabozo de Gideon)", "Crawlspace (Gideon dungeon)", "Crawlspace (Gideon dungeon)", "Crawlspace (Gideon dungeon) 사다리방 (기드온 던전)", "Crawlspace (Gideon dungeon) 暗门(基甸的洞穴)"}},
    {{"Crawlspace (secret shop)", "Crawlspace (secret shop)", "Crawlspace (secret shop)", "Mazmorra (tienda secreta)", "Crawlspace (secret shop)", "Crawlspace (secret shop)", "Crawlspace (secret shop) 사다리방 (암시장)", "Crawlspace (secret shop) 暗门(地下商店)"}},
    {{"Crawlspace (starting room)", "Crawlspace (starting room)", "Crawlspace (starting room)", "Mazmorra (sala de inicio)", "Crawlspace (starting room)", "Crawlspace (starting room)", "Crawlspace (starting room) 사다리방 (시작방)", "Crawlspace (starting room) 暗门(起始房间)"}},
    {{"Gravity", "Gravity", "Gravity", "Gravedad", "Gravity", "Gravity", "Gravity 중력", "Gravity 重力"}},
};

inline constexpr ConsoleLocalizedText kConsoleCompletionDebugFlagLocalizedDescriptions[] = {
    {{"Entity Positions", "Entity Positions", "Entity Positions", "Posiciones de Entidades", "Entity Positionen", "Entity Positions", "엔티티 위치 표시", "实体位置"}},
    {{"Grid", "Grid", "Grid", "Cuadricula", "Raster", "Grid", "격자 표시", "单元格"}},
    {{"Infinite HP", "Infinite HP", "Infinite HP", "Salud Infinita", "Unendliches Leben", "Infinite HP", "무한 체력", "无限血量"}},
    {{"High Damage", "High Damage", "High Damage", "Daño Alto", "Hoher Schaden", "High Damage", "공격력 상승", "高伤害"}},
    {{"Show Room Info", "Show Room Info", "Show Room Info", "Mostrar Informacion de sala", "Zeige Raum Informationen", "Show Room Info", "방 정보 표시", "显示房间信息"}},
    {{"Show Hitspheres", "Show Hitspheres", "Show Hitspheres", "Mostrar Hitspheres", "Zeige Treffersphären", "Show Hitspheres", "피격 범위 표시", "显示碰撞箱"}},
    {{"Show Damage Values", "Show Damage Values", "Show Damage Values", "Mostrar Valores de Daño", "Zeige Schadenswerte", "Show Damage Values", "피해량 표시", "显示伤害"}},
    {{"Infinite Item Charges", "Infinite Item Charges", "Infinite Item Charges", "Cargas de Objeto Infinitas", "Unendliche Gegenstandsladung", "Infinite Item Charges", "아이템 상시 충전", "无限充能"}},
    {{"High Luck", "High Luck", "High Luck", "Suerte Alta", "Großes Glück", "High Luck", "행운 상승", "高幸运"}},
    {{"Quick Kill", "Quick Kill", "Quick Kill", "Muerte Rápida", "Schnelles töten", "Quick Kill", "빠른 처치", "快速消灭"}},
    {{"Grid Info", "Grid Info", "Grid Info", "Informacion de Cuadricula", "Raster-Informationen", "Grid Info", "격자 정보", "单元格位置"}},
    {{"Player Item Info", "Player Item Info", "Player Item Info", "Informacion del Objeto de Jugador", "Spieler Gegenstands-Informationen", "Player Item Info", "플레이어 아이템 정보", "角色道具信息"}},
    {{"Show Grid Collision Points", "Show Grid Collision Points", "Show Grid Collision Points", "Mostrar Puntos de Colision de Cuadricula", "Zeige Raster Kollisionspunkte", "Show Grid Collision Points", "격자 충돌점 표시", "显示单元格碰撞点"}},
    {{"Show Lua Memory Usage", "Show Lua Memory Usage", "Show Lua Memory Usage", "Mostrar uso de Memoria Lua", "Zeige Lua Arbeitsspeicher Nutzung", "Show Lua Memory Usage", "Lua 메모리 사용량 표시", "显示Lua内存使用情况"}},
};

inline constexpr ConsoleLocalizedText kConsoleCompletionComboLocalizedDescriptions[] = {
    {{"Treasure", "Treasure", "Treasure", "Tesoro", "Schatz", "Treasure", "보물방", "宝箱房"}},
    {{"Shop", "Shop", "Shop", "Tienda", "Shop", "Shop", "상점", "商店"}},
    {{"Boss", "Boss", "Boss", "Jefe", "Boss", "Boss", "보스방", "头目房"}},
    {{"Devil", "Devil", "Devil", "Diablo", "Teufel", "Devil", "악마방", "恶魔房"}},
    {{"Angel", "Angel", "Angel", "Ángel", "Engel", "Angel", "천사방", "天使房"}},
    {{"Secret", "Secret", "Secret", "Secreta", "Geheimnis", "Secret", "비밀방", "隐藏房"}},
    {{"Library", "Library", "Library", "Biblioteca", "Bücherei", "Library", "책방", "图书馆"}},
    {{"Challenge", "Challenge", "Challenge", "Desafío", "Herausvorderung", "Challenge", "도전방", "挑战房"}},
    {{"Golden Chest", "Golden Chest", "Golden Chest", "Cofre Dorado", "Goldene Truhe", "Golden Chest", "황금 상자", "金箱子"}},
    {{"Red Chest", "Red Chest", "Red Chest", "Cofre rojo", "Rote Truhe", "Red Chest", "빨간 상자", "红箱子"}},
    {{"Beggar", "Beggar", "Beggar", "Mendigo", "Bettler", "Beggar", "거지", "乞丐"}},
    {{"Demon Beggar", "Demon Beggar", "Demon Beggar", "Mendigo Demoníaco", "Dämonen Bettler", "Demon Beggar", "익마 거지", "恶魔乞丐"}},
    {{"Curse", "Curse", "Curse", "Maldicion", "Fluch", "Curse", "저주방", "诅咒房"}},
    {{"Key Master", "Key Master", "Key Master", "Mendigo de Llaves", "Schlüsselmeister", "Key Master", "열쇠 거지", "钥匙大师"}},
    {{"Boss Rush", "Boss Rush", "Boss Rush", "Desafío de Jefes", "Boss Ansturm", "Boss Rush", "보스 러시", "头目车轮战"}},
    {{"Dungeon", "Dungeon", "Dungeon", "Mazmorra", "Verlies", "Dungeon", "던전", "夹层"}},
};

inline constexpr ConsoleCompletionCatalogEntry kConsoleCompletionStageEntries[] = {
    {"1", "Basement I", nullptr},
    {"1a", "Cellar I", nullptr},
    {"1b", "Burning Basement I", nullptr},
    {"1c", "Downpour I", nullptr},
    {"1d", "Dross I", nullptr},
    {"2", "Basement II", nullptr},
    {"2a", "Cellar II", nullptr},
    {"2b", "Burning Basement II", nullptr},
    {"2c", "Downpour II", nullptr},
    {"2d", "Dross II", nullptr},
    {"3", "Caves I", nullptr},
    {"3a", "Catacombs I", nullptr},
    {"3b", "Flooded Caves I", nullptr},
    {"3c", "Mines I", nullptr},
    {"3d", "Ashpit I", nullptr},
    {"4", "Caves II", nullptr},
    {"4a", "Catacombs II", nullptr},
    {"4b", "Flooded Caves II", nullptr},
    {"4c", "Mines II", nullptr},
    {"4d", "Ashpit II", nullptr},
    {"5", "Depths I", nullptr},
    {"5a", "Necropolis I", nullptr},
    {"5b", "Dank Depths I", nullptr},
    {"5c", "Mausoleum I", nullptr},
    {"5d", "Gehenna I", nullptr},
    {"6", "Depths II", nullptr},
    {"6a", "Necropolis II", nullptr},
    {"6b", "Dank Depths II", nullptr},
    {"6c", "Mausoleum II", nullptr},
    {"6d", "Gehenna II", nullptr},
    {"7", "Womb I", nullptr},
    {"7a", "Utero I", nullptr},
    {"7b", "Scarred Womb I", nullptr},
    {"7c", "Corpse I", nullptr},
    {"8", "Womb II", nullptr},
    {"8a", "Utero II", nullptr},
    {"8b", "Scarred Womb II", nullptr},
    {"8c", "Corpse II", nullptr},
    {"9", "\?\?\? / Blue Womb", &kConsoleStageLocalizedDescriptions[0]},
    {"10", "Sheol", nullptr},
    {"10a", "Cathedral", nullptr},
    {"11", "Dark Room", nullptr},
    {"11a", "Chest", nullptr},
    {"12", "The Void", nullptr},
    {"13", "Home (day)", &kConsoleStageLocalizedDescriptions[1]},
    {"13a", "Home (night)", &kConsoleStageLocalizedDescriptions[2]},
};

inline constexpr ConsoleStageCompletionRule kConsoleCompletionStageRules[] = {
    {"1", "Basement I", "BASEMENT_NAME", " I", nullptr},
    {"1a", "Cellar I", "CELLAR_NAME", " I", nullptr},
    {"1b", "Burning Basement I", "BURNING_BASEMENT_NAME", " I", nullptr},
    {"1c", "Downpour I", "DOWNPOUR_NAME", " I", nullptr},
    {"1d", "Dross I", "DROSS_NAME", " I", nullptr},
    {"2", "Basement II", "BASEMENT_NAME", " II", nullptr},
    {"2a", "Cellar II", "CELLAR_NAME", " II", nullptr},
    {"2b", "Burning Basement II", "BURNING_BASEMENT_NAME", " II", nullptr},
    {"2c", "Downpour II", "DOWNPOUR_NAME", " II", nullptr},
    {"2d", "Dross II", "DROSS_NAME", " II", nullptr},
    {"3", "Caves I", "CAVES_NAME", " I", nullptr},
    {"3a", "Catacombs I", "CATACOMBS_NAME", " I", nullptr},
    {"3b", "Flooded Caves I", "FLOODED_CAVES_NAME", " I", nullptr},
    {"3c", "Mines I", "MINES_NAME", " I", nullptr},
    {"3d", "Ashpit I", "ASHPIT_NAME", " I", nullptr},
    {"4", "Caves II", "CAVES_NAME", " II", nullptr},
    {"4a", "Catacombs II", "CATACOMBS_NAME", " II", nullptr},
    {"4b", "Flooded Caves II", "FLOODED_CAVES_NAME", " II", nullptr},
    {"4c", "Mines II", "MINES_NAME", " II", nullptr},
    {"4d", "Ashpit II", "ASHPIT_NAME", " II", nullptr},
    {"5", "Depths I", "DEPTHS_NAME", " I", nullptr},
    {"5a", "Necropolis I", "NECROPOLIS_NAME", " I", nullptr},
    {"5b", "Dank Depths I", "DANK_DEPTHS_NAME", " I", nullptr},
    {"5c", "Mausoleum I", "MAUSOLEUM_NAME", " I", nullptr},
    {"5d", "Gehenna I", "GEHENNA_NAME", " I", nullptr},
    {"6", "Depths II", "DEPTHS_NAME", " II", nullptr},
    {"6a", "Necropolis II", "NECROPOLIS_NAME", " II", nullptr},
    {"6b", "Dank Depths II", "DANK_DEPTHS_NAME", " II", nullptr},
    {"6c", "Mausoleum II", "MAUSOLEUM_NAME", " II", nullptr},
    {"6d", "Gehenna II", "GEHENNA_NAME", " II", nullptr},
    {"7", "Womb I", "WOMB_NAME", " I", nullptr},
    {"7a", "Utero I", "UTERO_NAME", " I", nullptr},
    {"7b", "Scarred Womb I", "SCARRED_WOMB_NAME", " I", nullptr},
    {"7c", "Corpse I", "CORPSE_NAME", " I", nullptr},
    {"8", "Womb II", "WOMB_NAME", " II", nullptr},
    {"8a", "Utero II", "UTERO_NAME", " II", nullptr},
    {"8b", "Scarred Womb II", "SCARRED_WOMB_NAME", " II", nullptr},
    {"8c", "Corpse II", "CORPSE_NAME", " II", nullptr},
    {"9", "\?\?\? / Blue Womb", nullptr, "", &kConsoleStageLocalizedDescriptions[0]},
    {"10", "Sheol", "SHEOL_NAME", "", nullptr},
    {"10a", "Cathedral", "CATHEDRAL_NAME", "", nullptr},
    {"11", "Dark Room", "DARK_ROOM_NAME", "", nullptr},
    {"11a", "Chest", "CHEST_NAME", "", nullptr},
    {"12", "The Void", "THE_VOID_NAME", "", nullptr},
    {"13", "Home (day)", nullptr, "", &kConsoleStageLocalizedDescriptions[1]},
    {"13a", "Home (night)", nullptr, "", &kConsoleStageLocalizedDescriptions[2]},
};

inline constexpr ConsoleCompletionCatalogEntry kConsoleCompletionGreedStageEntries[] = {
    {"1", "Basement", nullptr},
    {"1a", "Cellar", nullptr},
    {"1b", "Burning Basement", nullptr},
    {"2", "Caves", nullptr},
    {"2a", "Catacombs", nullptr},
    {"2b", "Flooded Caves", nullptr},
    {"3", "Depths", nullptr},
    {"3a", "Necropolis", nullptr},
    {"3b", "Dank Depths", nullptr},
    {"4", "Womb", nullptr},
    {"4a", "Utero", nullptr},
    {"4b", "Scarred Womb", nullptr},
    {"5", "Sheol", nullptr},
    {"6", "The Shop", nullptr},
    {"7", "Ultra Greed", nullptr},
};

inline constexpr ConsoleStageCompletionRule kConsoleCompletionGreedStageRules[] = {
    {"1", "Basement", "BASEMENT_NAME", "", nullptr},
    {"1a", "Cellar", "CELLAR_NAME", "", nullptr},
    {"1b", "Burning Basement", "BURNING_BASEMENT_NAME", "", nullptr},
    {"2", "Caves", "CAVES_NAME", "", nullptr},
    {"2a", "Catacombs", "CATACOMBS_NAME", "", nullptr},
    {"2b", "Flooded Caves", "FLOODED_CAVES_NAME", "", nullptr},
    {"3", "Depths", "DEPTHS_NAME", "", nullptr},
    {"3a", "Necropolis", "NECROPOLIS_NAME", "", nullptr},
    {"3b", "Dank Depths", "DANK_DEPTHS_NAME", "", nullptr},
    {"4", "Womb", "WOMB_NAME", "", nullptr},
    {"4a", "Utero", "UTERO_NAME", "", nullptr},
    {"4b", "Scarred Womb", "SCARRED_WOMB_NAME", "", nullptr},
    {"5", "Sheol", "SHEOL_NAME", "", nullptr},
    {"6", "The Shop", "THE_SHOP_NAME", "", nullptr},
    {"7", "Ultra Greed", "ULTRA_GREED_NAME", "", nullptr},
};

inline constexpr ConsoleCompletionCatalogEntry kConsoleCompletionGridEntries[] = {
    {"0.10", "Decoration A", &kConsoleCompletionGridLocalizedDescriptions[0]},
    {"0.20", "Decoration B", &kConsoleCompletionGridLocalizedDescriptions[1]},
    {"0.30", "Decoration C", &kConsoleCompletionGridLocalizedDescriptions[2]},
    {"1000", "Rock", &kConsoleCompletionGridLocalizedDescriptions[3]},
    {"1000.1000", "Rock (connecting)", &kConsoleCompletionGridLocalizedDescriptions[4]},
    {"1001", "Bomb Rock", &kConsoleCompletionGridLocalizedDescriptions[5]},
    {"1002", "Alt Rock", &kConsoleCompletionGridLocalizedDescriptions[6]},
    {"1003", "Tinted Rock", &kConsoleCompletionGridLocalizedDescriptions[7]},
    {"1008", "Marked Skull", &kConsoleCompletionGridLocalizedDescriptions[8]},
    {"1009", "Event Rock", &kConsoleCompletionGridLocalizedDescriptions[9]},
    {"1010", "Spiked Rock", &kConsoleCompletionGridLocalizedDescriptions[10]},
    {"1011", "Fool's Gold Rock", &kConsoleCompletionGridLocalizedDescriptions[11]},
    {"1300", "TNT", &kConsoleCompletionGridLocalizedDescriptions[12]},
    {"1400", "Fire Place", &kConsoleCompletionGridLocalizedDescriptions[13]},
    {"1410", "Red Fire Place", &kConsoleCompletionGridLocalizedDescriptions[14]},
    {"1490", "Red Poop", &kConsoleCompletionGridLocalizedDescriptions[15]},
    {"1494", "Rainbow Poop", &kConsoleCompletionGridLocalizedDescriptions[16]},
    {"1495", "Corny Poop", &kConsoleCompletionGridLocalizedDescriptions[17]},
    {"1496", "Golden Poop", &kConsoleCompletionGridLocalizedDescriptions[18]},
    {"1497", "Black Poop", &kConsoleCompletionGridLocalizedDescriptions[19]},
    {"1498", "White Poop", &kConsoleCompletionGridLocalizedDescriptions[20]},
    {"1499", "Giant Poop", &kConsoleCompletionGridLocalizedDescriptions[21]},
    {"1500", "Poop", &kConsoleCompletionGridLocalizedDescriptions[22]},
    {"1501", "Charming Poop", &kConsoleCompletionGridLocalizedDescriptions[23]},
    {"1900", "Block", &kConsoleCompletionGridLocalizedDescriptions[24]},
    {"1901", "Pillar", &kConsoleCompletionGridLocalizedDescriptions[25]},
    {"1930", "Spikes", &kConsoleCompletionGridLocalizedDescriptions[26]},
    {"1930.100", "Sanguine Bond Spikes", &kConsoleCompletionGridLocalizedDescriptions[27]},
    {"1931", "Retractable Spikes", &kConsoleCompletionGridLocalizedDescriptions[28]},
    {"1931.1", "Retractable Spikes (down 1/5)", &kConsoleCompletionGridLocalizedDescriptions[29]},
    {"1931.2", "Retractable Spikes (down 2/5)", &kConsoleCompletionGridLocalizedDescriptions[30]},
    {"1931.3", "Retractable Spikes (down 3/5)", &kConsoleCompletionGridLocalizedDescriptions[31]},
    {"1931.4", "Retractable Spikes (down 4/5)", &kConsoleCompletionGridLocalizedDescriptions[32]},
    {"1931.5", "Retractable Spikes (down 5/5)", &kConsoleCompletionGridLocalizedDescriptions[33]},
    {"1931.6", "Retractable Spikes (up 1/5)", &kConsoleCompletionGridLocalizedDescriptions[34]},
    {"1931.7", "Retractable Spikes (up 2/5)", &kConsoleCompletionGridLocalizedDescriptions[35]},
    {"1931.8", "Retractable Spikes (up 3/5)", &kConsoleCompletionGridLocalizedDescriptions[36]},
    {"1931.9", "Retractable Spikes (up 4/5)", &kConsoleCompletionGridLocalizedDescriptions[37]},
    {"1931.10", "Retractable Spikes (up 5/5)", &kConsoleCompletionGridLocalizedDescriptions[38]},
    {"1940", "Cobweb", &kConsoleCompletionGridLocalizedDescriptions[39]},
    {"1999", "Invisible Block", &kConsoleCompletionGridLocalizedDescriptions[40]},
    {"3000", "Pit", &kConsoleCompletionGridLocalizedDescriptions[41]},
    {"3001", "Fissure Spawner", &kConsoleCompletionGridLocalizedDescriptions[42]},
    {"3002", "Event Rail", &kConsoleCompletionGridLocalizedDescriptions[43]},
    {"3009", "Event Pit", &kConsoleCompletionGridLocalizedDescriptions[44]},
    {"4000", "Key Block", &kConsoleCompletionGridLocalizedDescriptions[45]},
    {"4500", "Pressure Plate", &kConsoleCompletionGridLocalizedDescriptions[46]},
    {"4500.1", "Reward Plate", &kConsoleCompletionGridLocalizedDescriptions[47]},
    {"4500.2", "Greed Plate", &kConsoleCompletionGridLocalizedDescriptions[48]},
    {"4500.3", "Rail Plate", &kConsoleCompletionGridLocalizedDescriptions[49]},
    {"4500.9", "Kill Plate", &kConsoleCompletionGridLocalizedDescriptions[50]},
    {"4500.10", "Event Plate (group 0)", &kConsoleCompletionGridLocalizedDescriptions[51]},
    {"4500.11", "Event Plate (group 1)", &kConsoleCompletionGridLocalizedDescriptions[52]},
    {"4500.12", "Event Plate (group 2)", &kConsoleCompletionGridLocalizedDescriptions[53]},
    {"4500.13", "Event Plate (group 3)", &kConsoleCompletionGridLocalizedDescriptions[54]},
    {"5000", "Devil Statue", &kConsoleCompletionGridLocalizedDescriptions[55]},
    {"5001", "Angel Statue", &kConsoleCompletionGridLocalizedDescriptions[56]},
    {"6000", "Rail (horizontal)", &kConsoleCompletionGridLocalizedDescriptions[57]},
    {"6000.1", "Rail (vertical)", &kConsoleCompletionGridLocalizedDescriptions[58]},
    {"6000.2", "Rail (down-to-right)", &kConsoleCompletionGridLocalizedDescriptions[59]},
    {"6000.3", "Rail (down-to-left)", &kConsoleCompletionGridLocalizedDescriptions[60]},
    {"6000.4", "Rail (up-to-right)", &kConsoleCompletionGridLocalizedDescriptions[61]},
    {"6000.5", "Rail (up-to-left)", &kConsoleCompletionGridLocalizedDescriptions[62]},
    {"6000.6", "Rail (crossroad)", &kConsoleCompletionGridLocalizedDescriptions[63]},
    {"6000.7", "Rail (end-left)", &kConsoleCompletionGridLocalizedDescriptions[64]},
    {"6000.8", "Rail (end-right)", &kConsoleCompletionGridLocalizedDescriptions[65]},
    {"6000.9", "Rail (end-up)", &kConsoleCompletionGridLocalizedDescriptions[66]},
    {"6000.10", "Rail (end-down)", &kConsoleCompletionGridLocalizedDescriptions[67]},
    {"6000.16", "Rail (cart-left)", &kConsoleCompletionGridLocalizedDescriptions[68]},
    {"6000.17", "Rail (cart-up)", &kConsoleCompletionGridLocalizedDescriptions[69]},
    {"6000.32", "Rail (cart-right)", &kConsoleCompletionGridLocalizedDescriptions[70]},
    {"6000.33", "Rail (cart-down)", &kConsoleCompletionGridLocalizedDescriptions[71]},
    {"6000.80", "Mineshaft Rail (horizontal 1)", &kConsoleCompletionGridLocalizedDescriptions[72]},
    {"6000.81", "Mineshaft Rail (vertical 1)", &kConsoleCompletionGridLocalizedDescriptions[73]},
    {"6000.82", "Mineshaft Rail (down-to-right 1)", &kConsoleCompletionGridLocalizedDescriptions[74]},
    {"6000.83", "Mineshaft Rail (down-to-left 1)", &kConsoleCompletionGridLocalizedDescriptions[75]},
    {"6000.84", "Mineshaft Rail (up-to-right 1)", &kConsoleCompletionGridLocalizedDescriptions[76]},
    {"6000.85", "Mineshaft Rail (up-to-left 1)", &kConsoleCompletionGridLocalizedDescriptions[77]},
    {"6000.96", "Mineshaft Rail (horizontal 2)", &kConsoleCompletionGridLocalizedDescriptions[78]},
    {"6000.97", "Mineshaft Rail (vertical 2)", &kConsoleCompletionGridLocalizedDescriptions[79]},
    {"6000.98", "Mineshaft Rail (down-to-right 2)", &kConsoleCompletionGridLocalizedDescriptions[80]},
    {"6000.99", "Mineshaft Rail (down-to-left 2)", &kConsoleCompletionGridLocalizedDescriptions[81]},
    {"6000.100", "Mineshaft Rail (up-to-right 2)", &kConsoleCompletionGridLocalizedDescriptions[82]},
    {"6000.101", "Mineshaft Rail (up-to-left 2)", &kConsoleCompletionGridLocalizedDescriptions[83]},
    {"6000.112", "Mineshaft Rail (horizontal 3)", &kConsoleCompletionGridLocalizedDescriptions[84]},
    {"6000.113", "Mineshaft Rail (vertical 3)", &kConsoleCompletionGridLocalizedDescriptions[85]},
    {"6001", "Rail Pit (horizontal)", &kConsoleCompletionGridLocalizedDescriptions[86]},
    {"6001.1", "Rail Pit (vertical)", &kConsoleCompletionGridLocalizedDescriptions[87]},
    {"6001.2", "Rail Pit (down-to-right)", &kConsoleCompletionGridLocalizedDescriptions[88]},
    {"6001.3", "Rail Pit (down-to-left)", &kConsoleCompletionGridLocalizedDescriptions[89]},
    {"6001.4", "Rail Pit (up-to-right)", &kConsoleCompletionGridLocalizedDescriptions[90]},
    {"6001.5", "Rail Pit (up-to-left)", &kConsoleCompletionGridLocalizedDescriptions[91]},
    {"6001.6", "Rail Pit (crossroad)", &kConsoleCompletionGridLocalizedDescriptions[92]},
    {"6001.16", "Rail Pit (cart-left)", &kConsoleCompletionGridLocalizedDescriptions[93]},
    {"6001.17", "Rail Pit (cart-up)", &kConsoleCompletionGridLocalizedDescriptions[94]},
    {"6001.32", "Rail Pit (cart-right)", &kConsoleCompletionGridLocalizedDescriptions[95]},
    {"6001.33", "Rail Pit (cart-down)", &kConsoleCompletionGridLocalizedDescriptions[96]},
    {"6100", "Teleporter (square)", &kConsoleCompletionGridLocalizedDescriptions[97]},
    {"6100.1", "Teleporter (moon)", &kConsoleCompletionGridLocalizedDescriptions[98]},
    {"6100.2", "Teleporter (rhombus)", &kConsoleCompletionGridLocalizedDescriptions[99]},
    {"6100.3", "Teleporter (M)", &kConsoleCompletionGridLocalizedDescriptions[100]},
    {"6100.4", "Teleporter (pentagram)", &kConsoleCompletionGridLocalizedDescriptions[101]},
    {"6100.5", "Teleporter (cross)", &kConsoleCompletionGridLocalizedDescriptions[102]},
    {"6100.6", "Teleporter (triangle)", &kConsoleCompletionGridLocalizedDescriptions[103]},
    {"9000", "Trap Door", &kConsoleCompletionGridLocalizedDescriptions[104]},
    {"9000.1", "Void Portal", &kConsoleCompletionGridLocalizedDescriptions[105]},
    {"9100", "Crawlspace", &kConsoleCompletionGridLocalizedDescriptions[106]},
    {"9100.1", "Crawlspace (Gideon dungeon)", &kConsoleCompletionGridLocalizedDescriptions[107]},
    {"9100.2", "Crawlspace (secret shop)", &kConsoleCompletionGridLocalizedDescriptions[108]},
    {"9100.3", "Crawlspace (starting room)", &kConsoleCompletionGridLocalizedDescriptions[109]},
    {"10000", "Gravity", &kConsoleCompletionGridLocalizedDescriptions[110]},
};

inline constexpr ConsoleCompletionCatalogEntry kConsoleCompletionDebugFlagEntries[] = {
    {"1", "Entity Positions", &kConsoleCompletionDebugFlagLocalizedDescriptions[0]},
    {"2", "Grid", &kConsoleCompletionDebugFlagLocalizedDescriptions[1]},
    {"3", "Infinite HP", &kConsoleCompletionDebugFlagLocalizedDescriptions[2]},
    {"4", "High Damage", &kConsoleCompletionDebugFlagLocalizedDescriptions[3]},
    {"5", "Show Room Info", &kConsoleCompletionDebugFlagLocalizedDescriptions[4]},
    {"6", "Show Hitspheres", &kConsoleCompletionDebugFlagLocalizedDescriptions[5]},
    {"7", "Show Damage Values", &kConsoleCompletionDebugFlagLocalizedDescriptions[6]},
    {"8", "Infinite Item Charges", &kConsoleCompletionDebugFlagLocalizedDescriptions[7]},
    {"9", "High Luck", &kConsoleCompletionDebugFlagLocalizedDescriptions[8]},
    {"10", "Quick Kill", &kConsoleCompletionDebugFlagLocalizedDescriptions[9]},
    {"11", "Grid Info", &kConsoleCompletionDebugFlagLocalizedDescriptions[10]},
    {"12", "Player Item Info", &kConsoleCompletionDebugFlagLocalizedDescriptions[11]},
    {"13", "Show Grid Collision Points", &kConsoleCompletionDebugFlagLocalizedDescriptions[12]},
    {"14", "Show Lua Memory Usage", &kConsoleCompletionDebugFlagLocalizedDescriptions[13]},
};

inline constexpr ConsoleCompletionCatalogEntry kConsoleCompletionComboEntries[] = {
    {"0.", "Treasure", &kConsoleCompletionComboLocalizedDescriptions[0]},
    {"1.", "Shop", &kConsoleCompletionComboLocalizedDescriptions[1]},
    {"2.", "Boss", &kConsoleCompletionComboLocalizedDescriptions[2]},
    {"3.", "Devil", &kConsoleCompletionComboLocalizedDescriptions[3]},
    {"4.", "Angel", &kConsoleCompletionComboLocalizedDescriptions[4]},
    {"5.", "Secret", &kConsoleCompletionComboLocalizedDescriptions[5]},
    {"6.", "Library", &kConsoleCompletionComboLocalizedDescriptions[6]},
    {"7.", "Challenge", &kConsoleCompletionComboLocalizedDescriptions[7]},
    {"8.", "Golden Chest", &kConsoleCompletionComboLocalizedDescriptions[8]},
    {"9.", "Red Chest", &kConsoleCompletionComboLocalizedDescriptions[9]},
    {"10.", "Beggar", &kConsoleCompletionComboLocalizedDescriptions[10]},
    {"11.", "Demon Beggar", &kConsoleCompletionComboLocalizedDescriptions[11]},
    {"12.", "Curse", &kConsoleCompletionComboLocalizedDescriptions[12]},
    {"13.", "Key Master", &kConsoleCompletionComboLocalizedDescriptions[13]},
    {"14.", "Boss Rush", &kConsoleCompletionComboLocalizedDescriptions[14]},
    {"15.", "Dungeon", &kConsoleCompletionComboLocalizedDescriptions[15]},
};

inline constexpr ConsoleCompletionCatalogEntry kConsoleCompletionDeliriousEntries[] = {
    {"0", "None", nullptr},
    {"1", "Monstro", nullptr},
    {"2", "Larry Jr.", nullptr},
    {"3", "Chub", nullptr},
    {"4", "Gurdy", nullptr},
    {"5", "Monstro II", nullptr},
    {"6", "Scolex", nullptr},
    {"7", "Famine", nullptr},
    {"8", "Pestilence", nullptr},
    {"9", "War", nullptr},
    {"10", "Death", nullptr},
    {"11", "The Duke of Flies", nullptr},
    {"12", "Peep", nullptr},
    {"13", "Loki", nullptr},
    {"14", "Blastocyst", nullptr},
    {"15", "Gemini", nullptr},
    {"16", "Fistula", nullptr},
    {"17", "Gish", nullptr},
    {"18", "Steven", nullptr},
    {"19", "C.H.A.D.", nullptr},
    {"20", "The Headless Horseman", nullptr},
    {"21", "The Fallen", nullptr},
    {"22", "The Hollow", nullptr},
    {"23", "Carrion Queen", nullptr},
    {"24", "Gurdy Jr.", nullptr},
    {"25", "The Husk", nullptr},
    {"26", "The Bloat", nullptr},
    {"27", "Lokii", nullptr},
    {"28", "The Blighted Ovum", nullptr},
    {"29", "Teratoma", nullptr},
    {"30", "The Widow", nullptr},
    {"31", "Mask of Infamy", nullptr},
    {"32", "The Wretched", nullptr},
    {"33", "Pin", nullptr},
    {"34", "Conquest", nullptr},
    {"35", "Daddy Long Legs", nullptr},
    {"36", "Triachnid", nullptr},
    {"37", "The Haunt", nullptr},
    {"38", "Dingle", nullptr},
    {"39", "Mega Maw", nullptr},
    {"40", "The Gate", nullptr},
    {"41", "Mega Fatty", nullptr},
    {"42", "The Cage", nullptr},
    {"43", "Mama Gurdy", nullptr},
    {"44", "Dark One", nullptr},
    {"45", "The Adversary", nullptr},
    {"46", "Polycephalus", nullptr},
    {"47", "Mr. Fred", nullptr},
    {"48", "Mega Satan", nullptr},
    {"49", "Gurgling", nullptr},
    {"50", "The Stain", nullptr},
    {"51", "Brownie", nullptr},
    {"52", "The Forsaken", nullptr},
    {"53", "Little Horn", nullptr},
    {"54", "Rag Man", nullptr},
    {"55", "Hush", nullptr},
    {"56", "Dangle", nullptr},
    {"57", "Turdling", nullptr},
    {"58", "The Frail", nullptr},
    {"59", "Rag Mega", nullptr},
    {"60", "Sisters Vis", nullptr},
    {"61", "Big Horn", nullptr},
};

inline constexpr ConsoleCompletionCatalogEntry kConsoleCompletionMacroEntries[] = {
    {"beast", "", nullptr},
    {"bigchest", "", nullptr},
    {"fc", "", nullptr},
    {"hud", "", nullptr},
    {"hush", "", nullptr},
    {"mom", "", nullptr},
    {"momh", "", nullptr},
    {"ms", "", nullptr},
    {"mss", "", nullptr},
    {"qk", "", nullptr},
    {"ug", "", nullptr},
    {"ugg", "", nullptr},
};

inline constexpr ConsoleLocalizedText kConsoleBuiltinCommandLocalizedDescriptions[] = {
    {{"Unlocks achievements", "Unlocks achievements", "Unlocks achievements", "Desbloquea Logros", "Schaltet Erfolge frei", "Unlocks achievements", "도전 과제 해금", "解锁成就"}},
    {{"Spawns a new player", "Spawns a new player", "Spawns a new player", "Genera un nuevo Jugador", "Erzeugt einen neuen Spieler", "Spawns a new player", "새 플레이어 생성", "生成一个玩家实体"}},
    {{"Start a challenge run", "Start a challenge run", "Start a challenge run", "Iniciar nueva Partida de Desafío", "Starten Sie einen Herausforderungs-Spiel", "Start a challenge run", "챌린지 실행", "开始一局新的挑战"}},
    {{"Clear unneeded bestiary data to reduce save file size", "Clear unneeded bestiary data to reduce save file size", "Clear unneeded bestiary data to reduce save file size", "Clear unneeded bestiary data to reduce save file size", "Clear unneeded bestiary data to reduce save file size", "Clear unneeded bestiary data to reduce save file size", "Clear unneeded bestiary data to reduce save file size", "Clear unneeded bestiary data to reduce save file size"}},
    {{"Clear the debug console", "Clear the debug console", "Clear the debug console", "Limpiar la consola", "Leere die Entwicklerkonsole", "Clear the debug console", "디버그 콘솔 청소", "清空控制台"}},
    {{"Clear the sprite cache", "Clear the sprite cache", "Clear the sprite cache", "Limpiar caché de sprites", "Leere den Grafik-Zwischenspeicher", "Clear the sprite cache", "스프라이트 캐시 삭제", "清除精灵图缓存"}},
    {{"Clear easter egg seeds in the current run", "Clear easter egg seeds in the current run", "Clear easter egg seeds in the current run", "Limpiar semillas \"easter egg\" de la partida actual", "Clear easter egg seeds in the current run", "Clear easter egg seeds in the current run", "현재 게임의 이스터 에그 시드 제거", "清除当前游戏的彩蛋种子"}},
    {{"Give items from a specified pool", "Give items from a specified pool", "Give items from a specified pool", "Otorga objetos de una pool especificada", "Give items from a specified pool", "Give items from a specified pool", "지정한 배열의 아이템 지급", "获得一个道具池中多个随机道具"}},
    {{"Copy previous commands to clipboard", "Copy previous commands to clipboard", "Copy previous commands to clipboard", "Copia los comandos anteriores al portapapeles", "Copy previous commands to clipboard", "Copy previous commands to clipboard", "이전 명령어를 클립보드에 복사", "复制之前输入的指定数量的命令至剪贴板"}},
    {{"Give the player random costumes", "Give the player random costumes", "Give the player random costumes", "Otorga al jugador trajes aleatorios", "Give the player random costumes", "Give the player random costumes", "캐릭터에게 무작위 코스튬을 지급", "给予角色随机角色形象"}},
    {{"Add curses to the current run", "Add curses to the current run", "Add curses to the current run", "Añade maldiciones a la partida actual", "Add curses to the current run", "Add curses to the current run", "현재 게임에 저주 추가", "为游戏添加诅咒效果"}},
    {{"Play a cutscene", "Play a cutscene", "Play a cutscene", "Reproducir cinematica", "Play a cutscene", "Play a cutscene", "컷신 재생", "播放过场动画"}},
    {{"Enable a debug flag", "Enable a debug flag", "Enable a debug flag", "Activar un Debug Flag", "Enable a debug flag", "Enable a debug flag", "디버그 플래그 활성화", "启用调试标记"}},
    {{"Force Delirious to be a certain boss", "Force Delirious to be a certain boss", "Force Delirious to be a certain boss", "Forzar Delirious a volverse un Jefe determinado", "Force Delirious to be a certain boss", "Force Delirious to be a certain boss", "정신착란이 생성하는 보스를 강제로 설정", "强制设定精神错乱为某个头目"}},
    {{"Unlock all easter egg seeds", "Unlock all easter egg seeds", "Unlock all easter egg seeds", "Desbloquea todas las semillas \"easter egg\"", "Unlock all easter egg seeds", "Unlock all easter egg seeds", "모든 이스터 에그 시드 해금", "解锁所有彩蛋种子"}},
    {{"Force a room to be used in level generator", "Force a room to be used in level generator", "Force a room to be used in level generator", "Forzar el uso de una sala en el generador de niveles", "Force a room to be used in level generator", "Force a room to be used in level generator", "지정한 방을 레벨 생성기가 강제로 사용하도록 설정", "强制在楼层生成时使用房间布局"}},
    {{"Closes and reopens the game", "Closes and reopens the game", "Closes and reopens the game", "Reiniciar el juego", "Closes and reopens the game", "Closes and reopens the game", "게임을 완전히 재시작", "关闭并重新打开游戏"}},
    {{"Give the character a TemporaryEffect", "Give the character a TemporaryEffect", "Give the character a TemporaryEffect", "Give the character a TemporaryEffect", "Give the character a TemporaryEffect", "Give the character a TemporaryEffect", "Give the character a TemporaryEffect", "Give the character a TemporaryEffect"}},
    {{"Give the character items, trinkets, cards, and pills", "Give the character items, trinkets, cards, and pills", "Give the character items, trinkets, cards, and pills", "Otorga al jugador objetos, trinkets, cartas, y pildoras", "Give the character items, trinkets, cards, and pills", "Give the character items, trinkets, cards, and pills", "캐릭터에게 아이템, 장신구, 카드 또는 알약을 지급", "给予角色道具、饰品、卡牌或胶囊"}},
    {{"Give player 2 items, trinkets, cards, and pills", "Give player 2 items, trinkets, cards, and pills", "Give player 2 items, trinkets, cards, and pills", "Otorga al segundo jugador objetos, trinkets, cartas, y pildoras", "Give player 2 items, trinkets, cards, and pills", "Give player 2 items, trinkets, cards, and pills", "2번째 캐릭터에게 아이템, 장신구, 카드 또는 알약을 지급", "给予第二角色道具、饰品、卡牌或胶囊"}},
    {{"Teleport to a new room", "Teleport to a new room", "Teleport to a new room", "Te teletransporta a una habitación nueva", "Teleport to a new room", "Teleport to a new room", "새 방으로 순간이동", "传送到新房间"}},
    {{"Spawn a grid entity", "Spawn a grid entity", "Spawn a grid entity", "Genera una entidad de cuadricula", "Spawn a grid entity", "Spawn a grid entity", "구조물 생성", "生成障碍物"}},
    {{"Get info about commands", "Get info about commands", "Get info about commands", "Obtiene información sobre los comandos", "Get info about commands", "Get info about commands", "명령어 정보", "获取命令帮助"}},
    {{"List current items", "List current items", "List current items", "Listar objetos actuales", "List current items", "List current items", "현재 아이템 목록", "输出已获得的道具"}},
    {{"Locks achievements", "Locks achievements", "Locks achievements", "Bloquear Logros", "Locks achievements", "Locks achievements", "도전 과제 잠금", "锁定成就"}},
    {{"Run Lua code", "Run Lua code", "Run Lua code", "Ejecutar codigo Lua", "Run Lua code", "Run Lua code", "Lua 코드 실행", "运行Lua代码"}},
    {{"Display lua memory usage", "Display lua memory usage", "Display lua memory usage", "Mostrar uso de memoria lua", "Display lua memory usage", "Display lua memory usage", "Lua 메모리 사용량 표시", "显示Lua内存用量"}},
    {{"Reload a Lua mod", "Reload a Lua mod", "Reload a Lua mod", "Recargar un mod Lua", "Reload a Lua mod", "Reload a Lua mod", "Lua 모드 새로고침", "重新加载Lua模组"}},
    {{"[EXPERIMENTAL] Reset the Lua context", "[EXPERIMENTAL] Reset the Lua context", "[EXPERIMENTAL] Reset the Lua context", "[EXPERIMENTAL] Reiniciar el contexto Lua", "[EXPERIMENTAL] Reset the Lua context", "[EXPERIMENTAL] Reset the Lua context", "[실험적] Lua 컨텍스트 초기화", "[实验性]重置Lua上下文"}},
    {{"Run a Lua file", "Run a Lua file", "Run a Lua file", "Ejecutar un archivo Lua", "Run a Lua file", "Run a Lua file", "Lua 파일 실행", "运行Lua文件"}},
    {{"Trigger a set of commands", "Trigger a set of commands", "Trigger a set of commands", "Activar un conjunto de comandos", "Trigger a set of commands", "Trigger a set of commands", "명령어 집합 실행", "运行一组命令"}},
    {{"Force Metronome to be a certain item", "Force Metronome to be a certain item", "Force Metronome to be a certain item", "Forzar Metronomo a ser un objeto especifico", "Force Metronome to be a certain item", "Force Metronome to be a certain item", "메트로놈이 발동할 아이템을 설정", "强制设定节拍器所生成的下个道具"}},
    {{"Change network delay", "Change network delay", "Change network delay", "Cambiar latencia de red", "Change network delay", "Change network delay", "네트워크 지연 조정", "更改网络延迟"}},
    {{"Initialize online coop", "Initialize online coop", "Initialize online coop", "Iniciar cooperativo online", "Initialize online coop", "Initialize online coop", "온라인 Co-op 시작", "初始化联机合作"}},
    {{"Play a sound effect", "Play a sound effect", "Play a sound effect", "Reproducir efecto de sonido", "Play a sound effect", "Play a sound effect", "효과음 재생", "播放音效"}},
    {{"[BROKEN] Start profiling", "[BROKEN] Start profiling", "[BROKEN] Start profiling", "[ROTO] Start profiling", "[BROKEN] Start profiling", "[BROKEN] Start profiling", "[손상] 데이터 추적 시작", "[损坏]启动采集"}},
    {{"[BROKEN] Stop profiling", "[BROKEN] Stop profiling", "[BROKEN] Stop profiling", "[BROKEN] Stop profiling", "[BROKEN] Stop profiling", "[BROKEN] Stop profiling", "[손상] 데이터 추적 중지", "[损坏]停止采集"}},
    {{"Remove an item", "Remove an item", "Remove an item", "Remover un objeto", "Remove an item", "Remove an item", "아이템 제거", "移除一个物品"}},
    {{"Remove an item", "Remove an item", "Remove an item", "Remover un objeto", "Remove an item", "Remove an item", "아이템 제거", "移除一个物品"}},
    {{"Removes a TemporaryEffect from the character", "Removes a TemporaryEffect from the character", "Removes a TemporaryEffect from the character", "Removes a TemporaryEffect from the character", "Removes a TemporaryEffect from the character", "Removes a TemporaryEffect from the character", "Removes a TemporaryEffect from the character", "Removes a TemporaryEffect from the character"}},
    {{"Reload floor overlays", "Reload floor overlays", "Reload floor overlays", "Recargar la capa de efectos visuales", "Reload floor overlays", "Reload floor overlays", "층 오버레이 새로고침", "重载楼层的图层"}},
    {{"Reload in-game shaders", "Reload in-game shaders", "Reload in-game shaders", "Recargar sombreadores del juego", "Reload in-game shaders", "Reload in-game shaders", "셰이더 새로고침", "重载游戏内光影"}},
    {{"Reload wisps", "Reload wisps", "Reload wisps", "Recargar fuegos fatuos", "Reload wisps", "Reload wisps", "위습 새로고침", "重载魂火与蝗虫"}},
    {{"Repeat prior commands", "Repeat prior commands", "Repeat prior commands", "Repetir comando anterior", "Repeat prior commands", "Repeat prior commands", "명령 반복 실행", "重复上一条命令"}},
    {{"Reseed the current floor", "Reseed the current floor", "Reseed the current floor", "Regenerar el piso actual", "Reseed the current floor", "Reseed the current floor", "현재 층을 무작위 시드로 교체", "使用随机种子替换当前楼层"}},
    {{"Restart on a new run", "Restart on a new run", "Restart on a new run", "Reiniciar en una nueva partida", "Restart on a new run", "Restart on a new run", "새 게임 시작", "重新开始一局新的游戏"}},
    {{"Restocks all shops", "Restocks all shops", "Restocks all shops", "Reabastecer tiendas", "Restocks all shops", "Restocks all shops", "모든 상점 재입고", "补充所有商店"}},
    {{"Reset game to last room state", "Reset game to last room state", "Reset game to last room state", "Restablecer juego al estado de la ultima sala", "Reset game to last room state", "Reset game to last room state", "게임 상태를 이전 방의 상태로 되돌리기", "回溯游戏状态至上一个房间"}},
    {{"Start a new run with the given seed", "Start a new run with the given seed", "Start a new run with the given seed", "Iniciar nueva partida con semilla establecida", "Start a new run with the given seed", "Start a new run with the given seed", "지정한 시드로 새 게임 시작", "使用选定种子重新开始一局新的游戏"}},
    {{"Spawn an entity", "Spawn an entity", "Spawn an entity", "Invocar entidad", "Spawn an entity", "Spawn an entity", "엔티티 생성", "生成实体"}},
    {{"Go to a stage", "Go to a stage", "Go to a stage", "Ir a un escenario", "Go to a stage", "Go to a stage", "스테이지 이동", "传送至楼层"}},
    {{"Print game time", "Print game time", "Print game time", "Imprimir tiempo de juego", "Print game time", "Print game time", "게임 시간 출력", "输出游戏时间"}},
    {{"Print list of bosses for current floor", "Print list of bosses for current floor", "Print list of bosses for current floor", "Imprimir lista de jefes del piso actual", "Print list of bosses for current floor", "Print list of bosses for current floor", "보스 목록 출력", "输出当前层的头目列表"}},
};

inline constexpr ConsoleLocalizedText kConsoleBuiltinCommandLocalizedHelpTexts[] = {
    {{"Unlocks achievements", "Unlocks achievements", "Unlocks achievements", "Desbloquea logros", "Schaltet Erfolge frei", "Unlocks achievements", "도전 과제 해금", "解锁成就"}},
    {{"Spawns a new player entity. On default, it spawns Isaac with controller ID 0.\nPlayer ID -1 lets you take control of a random enemy in the room.\nExample:\n(addplayer 7 1) Spawns Azazel and can be controlled with the second input device (controller 1 in most cases)", "Spawns a new player entity. On default, it spawns Isaac with controller ID 0.\nPlayer ID -1 lets you take control of a random enemy in the room.\nExample:\n(addplayer 7 1) Spawns Azazel and can be controlled with the second input device (controller 1 in most cases)", "Spawns a new player entity. On default, it spawns Isaac with controller ID 0.\nPlayer ID -1 lets you take control of a random enemy in the room.\nExample:\n(addplayer 7 1) Spawns Azazel and can be controlled with the second input device (controller 1 in most cases)", "Genera una nueva entidad de Jugador. Por defecto, genera a Isaac con ControllerId 0.\nPlayer ID -1 te permite tomar control de un enemigo aleatorio en la sala.\nEjemplo:\n(addplayer 7 1) Genera a Azazel y puede ser controlado con el segundo dispositivo de entrada (controlador 1 la mayoría de las veces)", "Erzeugt einen neuen Spieler. Standardmäßig spawnt Isaac mit der Controller-ID 0.\nMit der Spieler-ID -1 können Sie die Kontrolle über einen zufälligen Feind im Raum übernehmen.\nBeispiel:\n(addplayer 7 1) spawnt Azazel und kann mit dem zweiten Eingabegerät gesteuert werden ( in den meisten Fällen Controller 1)", "Spawns a new player entity. On default, it spawns Isaac with controller ID 0.\nPlayer ID -1 lets you take control of a random enemy in the room.\nExample:\n(addplayer 7 1) Spawns Azazel and can be controlled with the second input device (controller 1 in most cases)", "새 플레이어 엔티티를 생성합니다. 기본적으로 컨트롤러 ID가 0인 아이작을 생성합니다.\n플레이어 ID를 -1로 입력하면 방 안에 있는 무작위 적을 제어할 수 있습니다.\n예시:\n(addplayer 7 1)을 입력하면 아자젤을 생성하며, 2번째 입력 장치(대부분의 경우 컨트롤러 1)로 제어할 수 있습니다.", "生成一个玩家实体。默认参数会生成一个由ID为0的控制器操控的以撒。\ntype设为-1将会操控房间中随机敌人。\n例如：\n（addplayer 7 1）会生成一个阿撒泻勒，其由第二输入设备操控（大多数情况下控制器1即为第二输入设备）"}},
    {{"Stops the current run and starts a new run on a random seed with the given challenge ID.\nExample:\n(challenge 20) will start a new Purist challenge run.\n", "Stops the current run and starts a new run on a random seed with the given challenge ID.\nExample:\n(challenge 20) will start a new Purist challenge run.\n", "Stops the current run and starts a new run on a random seed with the given challenge ID.\nExample:\n(challenge 20) will start a new Purist challenge run.\n", "Detiene la partida actual e inicia una nueva en una semilla aleatoria con la ID del desafio proporcionada.\nEjemplo:\n(challenge 20) Iniciará una nueva partida del desafio \"Purista\".\n", "Stoppt das aktuellen Lauf und startet einen Neuen mit einem zufälligen Seed und der angegebenen Herausforderungs-ID.\nBeispiel:\n(challenge 20) startet die Puristen-Herausforderung.\n", "Stops the current run and starts a new run on a random seed with the given challenge ID.\nExample:\n(challenge 20) will start a new Purist challenge run.\n", "현재 게임을 중단하고 주어진 챌린지 ID로 무작위 시드에서 새 게임을 시작합니다.\n예시:\n(challenge 20)을 입력하면 '순수주의자' 챌린지를 실행합니다.\n", "结束当前游戏并以随机种子进行给定ID的挑战。\n例如：\n（challenge 20）\n开始一论新的返璞归真挑战。\n"}},
    {{"Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible).", "Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible).", "Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible).", "Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible).", "Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible).", "Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible).", "Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible).", "Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible)."}},
    {{"Clears all text currently displayed in the debug console. Only the line \"Repentance Console\" will remain.", "Clears all text currently displayed in the debug console. Only the line \"Repentance Console\" will remain.", "Clears all text currently displayed in the debug console. Only the line \"Repentance Console\" will remain.", "Borra todo el texto dentro de la consola. Solo permanecerá la linea \"Repentance Console\".", "Entfernt alle Texte die aktuell in der Entwicklerkonsole dargestellt werden. Nur die Zeile \"Repentance Console\" bleibt bestehen.", "Clears all text currently displayed in the debug console. Only the line \"Repentance Console\" will remain.", "디버그 콘솔에 표시된 모든 문자를 제거합니다. \"Repentance Console\"이라는 줄만 남습니다.", "清除控制台显示的所有文字。仍会保留“Repentance Console”。"}},
    {{"Clears the game's sprite cache. This can be useful for trying to deal with memory issues.\nThis also has the side effect of reloading modded sprites without needing a full game restart.", "Clears the game's sprite cache. This can be useful for trying to deal with memory issues.\nThis also has the side effect of reloading modded sprites without needing a full game restart.", "Clears the game's sprite cache. This can be useful for trying to deal with memory issues.\nThis also has the side effect of reloading modded sprites without needing a full game restart.", "Borra la caché de sprites del juego. Puede ser útil al intentar solucionar problemas de memoria.\nTambien permite recargar los sprites de mods sin tener que reiniciar el juego por completo.", "Leere den Grafik-Zwischenspeicher des Spiels. Dies kann bei Arbeitsspeicher Problemen helfen.\nDies hat zudem den Effekt das Grafiken von Mods neu geladen werden, ohne das Spiel neu starten zu müssen.", "Clears the game's sprite cache. This can be useful for trying to deal with memory issues.\nThis also has the side effect of reloading modded sprites without needing a full game restart.", "게임의 스프라이트 캐시를 제거합니다. 이 기능은 메모리 문제를 해결하는 데 유용할 수 있습니다.\n추가로, 게임을 재시작하지 않고 수정된 스프라이트를 다시 불러올 수 있습니다.", "清除游戏的精灵图缓存。可以用于尝试解决内存问题。\n副作用为无需完全重启游戏即可重新加载修改后的精灵图。"}},
    {{"Clears any \"special\" seed effects in the current run.\nExample:\nThe seed effect GFVE LLLL is applied in a run. Running clearseeds will remove this effect.", "Clears any \"special\" seed effects in the current run.\nExample:\nThe seed effect GFVE LLLL is applied in a run. Running clearseeds will remove this effect.", "Clears any \"special\" seed effects in the current run.\nExample:\nThe seed effect GFVE LLLL is applied in a run. Running clearseeds will remove this effect.", "Limpia cualquier efecto \"especial\" de semilla en la partida actual.\nEjemplo:\nIniciar una partida con la semilla GFVE LLLL aplicara su efecto. Ejecutar \"clearseeds\" removerá ese efecto.", "Clears any \"special\" seed effects in the current run.\nExample:\nThe seed effect GFVE LLLL is applied in a run. Running clearseeds will remove this effect.", "Clears any \"special\" seed effects in the current run.\nExample:\nThe seed effect GFVE LLLL is applied in a run. Running clearseeds will remove this effect.", "현재 게임에서 \"특별\" 시드의 효과를 제거합니다.\n예시:\nGFVE LLLL 시드의 효과가 적용된 게임에서 clearseeds를 입력하면 그 효과를 제거합니다.", "清除当前游戏的“特殊”种子效果。\n例如：\n使用种子GFVE LLLL开始一轮游戏。使用命令clearseeds会移除种子效果。"}},
    {{"Gives a specified number of items from a specified item pool.\nExample:\n(combo 4.6) will give six random items from the Angel item pool.\nNo, I don't know why they made a bespoke ID system for this one (1) command.", "Gives a specified number of items from a specified item pool.\nExample:\n(combo 4.6) will give six random items from the Angel item pool.\nNo, I don't know why they made a bespoke ID system for this one (1) command.", "Gives a specified number of items from a specified item pool.\nExample:\n(combo 4.6) will give six random items from the Angel item pool.\nNo, I don't know why they made a bespoke ID system for this one (1) command.", "Otorga un número especifico de objetos de una pool de objetos especifica.\nEjemplo:\n(combo 4.6) otorgara seis objetos aleatorios from the Angel item pool.\nNo, No sé por qué hicieron un sistema de ID a la medida para este comando.", "Gives a specified number of items from a specified item pool.\nExample:\n(combo 4.6) will give six random items from the Angel item pool.\nNo, I don't know why they made a bespoke ID system for this one (1) command.", "Gives a specified number of items from a specified item pool.\nExample:\n(combo 4.6) will give six random items from the Angel item pool.\nNo, I don't know why they made a bespoke ID system for this one (1) command.", "지정한 아이템 배열에서 정해진 개수만큼 아이템을 무작위로 지급합니다.\n예시:\n(combo 4.6)을 입력하면 천사방 배열에서 무작위로 6개의 아이템을 지급합니다.\n아, 왜 이 명령어 하나 때문에 따로 ID 체계를 만들었는지 모르겠습니다.", "获得选定道具池中的选定数量个随机道具。\n例如：\n（combo 4.6）会给予天使房道具池的六个随机道具。\n老天，我不知道他们为什么要为这一（1）个命令制作定制的ID系统。"}},
    {{"Copies a specified amount of previous console commands to the system clipboard.\nExample:\n(copy 3) will copy the previous three commands.", "Copies a specified amount of previous console commands to the system clipboard.\nExample:\n(copy 3) will copy the previous three commands.", "Copies a specified amount of previous console commands to the system clipboard.\nExample:\n(copy 3) will copy the previous three commands.", "Copia un número especifico de comandos anteriores de la consola al portapapeles del sistema.\nEjemplo:\n(copy 3) copiará los tres comandos anteriores.", "Copies a specified amount of previous console commands to the system clipboard.\nExample:\n(copy 3) will copy the previous three commands.", "Copies a specified amount of previous console commands to the system clipboard.\nExample:\n(copy 3) will copy the previous three commands.", "지정한 개수만큼 이전에 입력한 콘솔 명령어를 클립보드에 복사합니다.\n예시:\n(copy 3)을 입력하면 최근 3개의 명령어가 복사됩니다.", "复制之前输入的指定数量的命令至系统剪贴板。\n例如：\n（copy 3）会复制前三次输入。"}},
    {{"Gives the player a specified amount of random costumes.\nExample:\n(costumetest 34) will give the player 34 random costumes.", "Gives the player a specified amount of random costumes.\nExample:\n(costumetest 34) will give the player 34 random costumes.", "Gives the player a specified amount of random costumes.\nExample:\n(costumetest 34) will give the player 34 random costumes.", "Otorga al jugador una cantidad especifica de trajes aleatorios.\nEjemplo:\n(costumetest 34) otorgara al jugador 34 trajes aleatorios.", "Gives the player a specified amount of random costumes.\nExample:\n(costumetest 34) will give the player 34 random costumes.", "Gives the player a specified amount of random costumes.\nExample:\n(costumetest 34) will give the player 34 random costumes.", "지정한 개수만큼 캐릭터에게 무작위 코스튬을 지급합니다.\n예시:\n(costumetest 34)를 입력하면 캐릭터에게 34개의 무작위 코스튬을 지급합니다.", "角色随机获得选定数量个道具的角色形象。\n例如：\n（costumetest 34）会给与角色34个随机服饰。"}},
    {{"Permanently (until overridden) adds curses to the run. This command uses a bitmask- the curse with an ID of 1 is 1, 2 is 2, 3 is 4, 4 is 8, and so on. In this manner, desired curse ID's are tallied up and multiple can be enabled simultaneously.\nExample:\n(curse 96) will enable Curse of the Blind and Curse of the Maze simultaneously.", "Permanently (until overridden) adds curses to the run. This command uses a bitmask- the curse with an ID of 1 is 1, 2 is 2, 3 is 4, 4 is 8, and so on. In this manner, desired curse ID's are tallied up and multiple can be enabled simultaneously.\nExample:\n(curse 96) will enable Curse of the Blind and Curse of the Maze simultaneously.", "Permanently (until overridden) adds curses to the run. This command uses a bitmask- the curse with an ID of 1 is 1, 2 is 2, 3 is 4, 4 is 8, and so on. In this manner, desired curse ID's are tallied up and multiple can be enabled simultaneously.\nExample:\n(curse 96) will enable Curse of the Blind and Curse of the Maze simultaneously.", "Añade permanentemente (hasta ser anulado) una maldición a la partida. Este comando usa un bitmask- la maldición con una ID de 1 es 1, 2 es 2, 3 es 4, 4 es 8, etc. De esta manera, se suman las IDs de las maldiciones deseadas permitiendo habilitar multiples simultáneamente.\nEjemplo:\n(curse 96) activará la Maldición del ciego y la Maldición del Laberinto simultaneamente.", "Permanently (until overridden) adds curses to the run. This command uses a bitmask- the curse with an ID of 1 is 1, 2 is 2, 3 is 4, 4 is 8, and so on. In this manner, desired curse ID's are tallied up and multiple can be enabled simultaneously.\nExample:\n(curse 96) will enable Curse of the Blind and Curse of the Maze simultaneously.", "Permanently (until overridden) adds curses to the run. This command uses a bitmask- the curse with an ID of 1 is 1, 2 is 2, 3 is 4, 4 is 8, and so on. In this manner, desired curse ID's are tallied up and multiple can be enabled simultaneously.\nExample:\n(curse 96) will enable Curse of the Blind and Curse of the Maze simultaneously.", "게임에 영구적으로(덮어쓰기 전까지) 저주를 추가합니다. 이 명령어는 비트마스크를 사용하며, ID가 1인 저주는 1, 2는 2, 3은 4, 4는 8...과 같은 방식입니다. 이 방식으로 원하는 저주 ID를 계산하여 여러 저주를 동시에 활성화 할 수 있습니다.\n예시:\n(curse 96)을 입력하면 눈먼 자의 저주와 미로의 저주를 동시에 활성화합니다.", "为游戏永久添加诅咒（直至被覆写）。此命令使用位掩码——ID 为1的诅咒是1,2是2,3是4,4是8，依此类推。通过这种方式，所需的诅咒 ID 得以计算，并且可以同时启用多个。\n例如：\n（curse 96）会同时启用致盲诅咒和混乱诅咒。"}},
    {{"Immediately plays the specified cutscenne.\nExample:\n(cutscene 1) will immediately play the game's intro.", "Immediately plays the specified cutscenne.\nExample:\n(cutscene 1) will immediately play the game's intro.", "Immediately plays the specified cutscenne.\nExample:\n(cutscene 1) will immediately play the game's intro.", "Reproduce inmediatamente la cinematica especificada.\nEjemplo:\n(cutscene 1) reproducirá la intro del juego.", "Immediately plays the specified cutscenne.\nExample:\n(cutscene 1) will immediately play the game's intro.", "Immediately plays the specified cutscenne.\nExample:\n(cutscene 1) will immediately play the game's intro.", "지정한 컷신을 즉시 재생합니다.\n예시:\n(cutscene 1)을 입력하면 게임의 인트로를 즉시 재생합니다.", "立即播放选定的过场动画。\n例如：\n（cutscene 1）会立刻播放开场动画。"}},
    {{"Enables the specified debug flag.\nExample:\n(debug 3) will grant the player infinite HP.", "Enables the specified debug flag.\nExample:\n(debug 3) will grant the player infinite HP.", "Enables the specified debug flag.\nExample:\n(debug 3) will grant the player infinite HP.", "Activa la Debug Flag especifica.\nEjemplo:\n(debug 3) otorgará al jugador salud infinita.", "Enables the specified debug flag.\nExample:\n(debug 3) will grant the player infinite HP.", "Enables the specified debug flag.\nExample:\n(debug 3) will grant the player infinite HP.", "지정한 디버그 플래그를 활성화합니다.\n예시:\n(debug 3)을 입력하면 플레이어에게 무한 체력을 부여합니다.", "启用选定的调试标记。\n例如：\n（debug 3）会给予玩家无限的血量。"}},
    {{"Overrides the next boss the Delirious item will become.\nExample:\n(delirious 3) will force Delirious to be a Chub.", "Overrides the next boss the Delirious item will become.\nExample:\n(delirious 3) will force Delirious to be a Chub.", "Overrides the next boss the Delirious item will become.\nExample:\n(delirious 3) will force Delirious to be a Chub.", "Anula el próximo jefe en el que se convertirá el objeto Delirious.\nEjemplo:\n(delirious 3) forzará Delirious a transformarse en Chub.", "Overrides the next boss the Delirious item will become.\nExample:\n(delirious 3) will force Delirious to be a Chub.", "Overrides the next boss the Delirious item will become.\nExample:\n(delirious 3) will force Delirious to be a Chub.", "정신착란(액티브 아이템)이 생성하는 다음 보스를 설정합니다.\n예시:\n(delirious 3)을 입력하면 정신착란이 처브를 생성합니다.", "规定精神错乱（主动道具）所生成的下个跟班为所选值。\n例如：\n（delirious 3）会强制将精神错乱变形为胖蛆。"}},
    {{"PERMANENTLY unlocks all easter eggs in this save file.", "PERMANENTLY unlocks all easter eggs in this save file.", "PERMANENTLY unlocks all easter eggs in this save file.", "PERMANENTEMENTE desbloquea todos los easter eggs en este archivo de guardado.", "PERMANENTLY unlocks all easter eggs in this save file.", "PERMANENTLY unlocks all easter eggs in this save file.", "해당 저장파일에서 영구적으로 모든 이스터 에그가 해금됩니다.", " 永久 解锁此存档文件的所有彩蛋种子。"}},
    {{"Allows to set any room as \"forced room\". Said room gets weight of 1000, making it more likely to appear on floor with reseed command.", "Allows to set any room as \"forced room\". Said room gets weight of 1000, making it more likely to appear on floor with reseed command.", "Allows to set any room as \"forced room\". Said room gets weight of 1000, making it more likely to appear on floor with reseed command.", "Permite establecer cualquier sala como \"sala obligatoria\". Dicha sala tendra un peso de 1000, volviendola más probable que aparezca en el suelo con el comando reseed.", "Allows to set any room as \"forced room\". Said room gets weight of 1000, making it more likely to appear on floor with reseed command.", "Allows to set any room as \"forced room\". Said room gets weight of 1000, making it more likely to appear on floor with reseed command.", "어떤 방이든 \"forced room\"으로 설정합니다. 해당 방의 가중치를 1000으로 설정하여, reseed 명령어를 사용할 때 해당 방이 층에 등장할 가능성이 매우 높아집니다.", "设置参数指定的房间为“forced room”。 即将该房间权重设为1000，使得该房间在reseed命令下的楼层中更容易出现。"}},
    {{"Closes and reopens the game", "Closes and reopens the game", "Closes and reopens the game", "Cierra y vuelve a abrir el juego", "Closes and reopens the game", "Closes and reopens the game", "게임을 완전히 재시작", "关闭并重新打开游戏"}},
    {{"Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect.", "Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect.", "Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect.", "Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect.", "Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect.", "Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect.", "Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect.", "Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect."}},
    {{"Gives the main player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem c1) will give the player The Sad Onion.\n(giveitem t1) will give the player Gulp!\n(giveitem p1) will give the player a Bad Trip pill.\n(giveitem k1) will give the player 0 - The Fool.", "Gives the main player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem c1) will give the player The Sad Onion.\n(giveitem t1) will give the player Gulp!\n(giveitem p1) will give the player a Bad Trip pill.\n(giveitem k1) will give the player 0 - The Fool.", "Gives the main player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem c1) will give the player The Sad Onion.\n(giveitem t1) will give the player Gulp!\n(giveitem p1) will give the player a Bad Trip pill.\n(giveitem k1) will give the player 0 - The Fool.", "Otorga the jugador principal objetos, trinkets, cartas, y pildoras. Estos pueden ser por nombre o por prefijo. Los prefijos son (c) para objetos, (t) para trinkets, (T) para trinkets dorados, (p) para pildoras, (P) para pildoras de caballo, y (k) para cartas. La mayoría de objetos de bolsillo cuentan como cartas.Este comando también tiene una abreviatura (g).\nEjemplos:\n(giveitem c1) le dará al jugador Sad Onion.\n(giveitem t1) le dará al jugador ¡Gulp!\n(giveitem p1) le dará al jugador la pildora Mal viaje.\n(giveitem k1) le dará al jugador 0 - El Bufón.", "Gives the main player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem c1) will give the player The Sad Onion.\n(giveitem t1) will give the player Gulp!\n(giveitem p1) will give the player a Bad Trip pill.\n(giveitem k1) will give the player 0 - The Fool.", "Gives the main player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem c1) will give the player The Sad Onion.\n(giveitem t1) will give the player Gulp!\n(giveitem p1) will give the player a Bad Trip pill.\n(giveitem k1) will give the player 0 - The Fool.", "메인 캐릭터에게 아이템, 장신구, 카드 또는 알약을 지급합니다. 매개변수에는 이름이나 유형을 입력할 수 있습니다. (c)는 아이템을, (t)는 장신구를, (T)는 황금 장신구를, (p)는 알약을, (P)는 말약을, (k)는 카드를 의미합니다. 대부분의 포켓 아이템은 카드로 간주됩니다.\n이 명령어의 약자는 (g)입니다.\n예시:\n(giveitem c1)을 입력하면 캐릭터에게 눈물나는 양파를 지급합니다.\n(giveitem t1)은 캐릭터에게 삼킨 동전을 지급합니다.\n(giveitem p1)은 캐릭터에게 마약 환각 알약을 지급합니다.\n(giveitem k1)을 입력하면 0 - 바보를 지급합니다.", "给予主角色道具、饰品、卡牌或胶囊。变量可以输入名称或类型。类型（c）代表道具，（t）代表饰品，（k）代表卡牌，（p）代表胶囊。大多数消耗品均被视为卡牌。\n这个命令的缩写是（g）。\n例如\n（giveitem c1）会给予角色悲伤洋葱。\n（giveitem t1）会给予角色被吞下的硬币。\n（giveitem p1）会给予角色过激幻觉胶囊。\n（giveitem k1）会给予角色0-愚者。"}},
    {{"Gives the second player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem2 c1) will give the player The Sad Onion.\n(giveitem2 t1) will give the player Gulp!\n(giveitem2 p1) will give the player a Bad Trip pill.\n(giveitem2 k1) will give the player 0 - The Fool.", "Gives the second player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem2 c1) will give the player The Sad Onion.\n(giveitem2 t1) will give the player Gulp!\n(giveitem2 p1) will give the player a Bad Trip pill.\n(giveitem2 k1) will give the player 0 - The Fool.", "Gives the second player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem2 c1) will give the player The Sad Onion.\n(giveitem2 t1) will give the player Gulp!\n(giveitem2 p1) will give the player a Bad Trip pill.\n(giveitem2 k1) will give the player 0 - The Fool.", "Otorga al segundo jugador objetos, trinkets, cartas y pildoras. Estos pueden ser por nombre o por prefijo. Los prefijos son (c) para objetos, (t) para trinkets, (T) para trinkets dorados, (p) para pildoras, (P) para pildoras de caballo, y (k) para cartas. La mayoría de objetos de bolsillo cuentan como cartas.Este comando también tiene una abreviatura (g).\nEjemplos:\n(giveitem c1) le dará al jugador Sad Onion.\n(giveitem t1) le dará al jugador ¡Gulp!\n(giveitem p1) le dará al jugador la pildora Mal viaje.\n(giveitem k1) le dará al jugador 0 - El Bufón.", "Gives the second player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem2 c1) will give the player The Sad Onion.\n(giveitem2 t1) will give the player Gulp!\n(giveitem2 p1) will give the player a Bad Trip pill.\n(giveitem2 k1) will give the player 0 - The Fool.", "Gives the second player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem2 c1) will give the player The Sad Onion.\n(giveitem2 t1) will give the player Gulp!\n(giveitem2 p1) will give the player a Bad Trip pill.\n(giveitem2 k1) will give the player 0 - The Fool.", "2번째 캐릭터에게 아이템, 장신구, 카드 또는 알약을 지급합니다. 매개변수에는 이름이나 유형을 입력할 수 있습니다. (c)는 아이템을, (t)는 장신구를, (T)는 황금 장신구를, (p)는 알약을, (P)는 말약을, (k)는 카드를 의미합니다. 대부분의 포켓 아이템은 카드로 간주됩니다.\n이 명령어의 약자는 (g)입니다.\n예시:\n(giveitem c1)을 입력하면 캐릭터에게 눈물나는 양파를 지급합니다.\n(giveitem t1)은 캐릭터에게 삼킨 동전을 지급합니다.\n(giveitem p1)은 캐릭터에게 마약 환각 알약을 지급합니다.\n(giveitem k1)을 입력하면 0 - 바보를 지급합니다.", "给予第二角色道具、饰品、卡牌或胶囊。类型（c）代表道具，（t）代表饰品，（k）代表卡牌，（p）代表胶囊。大多数消耗品均被视为卡牌。\n这个命令的缩写是（g）。\n例如\n（giveitem2 c1）会给予角色悲伤洋葱。\n（giveitem2 t1）会给予角色被吞下的硬币。\n（giveitem2 p1）会给予角色过激幻觉胶囊。\n（giveitem2 k1）会给予角色0-愚者。"}},
    {{"Teleports the character to a new room. Use (d) for a standard room, (s) for a special room, or three numbers to teleport to an existing room on the floor.\nExample:\n(goto s.boss.1010) will go to a Monstro fight.", "Teleports the character to a new room. Use (d) for a standard room, (s) for a special room, or three numbers to teleport to an existing room on the floor.\nExample:\n(goto s.boss.1010) will go to a Monstro fight.", "Teleports the character to a new room. Use (d) for a standard room, (s) for a special room, or three numbers to teleport to an existing room on the floor.\nExample:\n(goto s.boss.1010) will go to a Monstro fight.", "Teletransporta al personaje a una nueva habitación. Usa (d) para una sala común, (s) para una sala especial, o tres numeros para teletransportarte a una sala existente del piso actual.\nEjemplo:\n(goto s.boss.1010) te llevará a la pelea de Monstro.", "Teleports the character to a new room. Use (d) for a standard room, (s) for a special room, or three numbers to teleport to an existing room on the floor.\nExample:\n(goto s.boss.1010) will go to a Monstro fight.", "Teleports the character to a new room. Use (d) for a standard room, (s) for a special room, or three numbers to teleport to an existing room on the floor.\nExample:\n(goto s.boss.1010) will go to a Monstro fight.", "캐릭터를 새 방으로 순간이동시킵니다. (d)는 일반 방을, (s)는 특별 방을, 숫자 세 개를 사용하면 현재 층에 존재하는 방으로 이동할 수 있습니다.\n예시:\n(goto s.boss.1010)을 입력하면 몬스트로 보스방으로 이동합니다.", "将角色传送到当前层特定地形的房间中。（d）代表普通房间，（s）代表特殊房间，（x）代表特定楼层的某些特殊房间布局\n例如：\n（goto s.boss.1010）将传送至萌死戳头目战房间。"}},
    {{"Spawns a new grid entity of the given ID at a random place in the room.", "Spawns a new grid entity of the given ID at a random place in the room.", "Spawns a new grid entity of the given ID at a random place in the room.", "Genera una nueva entidad de cuadricula de la ID especificada en un punto aleatorio de la sala.", "Spawns a new grid entity of the given ID at a random place in the room.", "Spawns a new grid entity of the given ID at a random place in the room.", "지정한 ID의 구조물을 임의의 위치에 생성합니다.", "以选定ID生成障碍物，其会出现在房间内随机位置。"}},
    {{"Retrieve further info about a command and its syntax.", "Retrieve further info about a command and its syntax.", "Retrieve further info about a command and its syntax.", "Proporciona información adicional sobre un comando y su sintaxis.", "Retrieve further info about a command and its syntax.", "Retrieve further info about a command and its syntax.", "명령어의 상세 정보와 사용법을 확인합니다.", "获取有关命令及其语法的信息。"}},
    {{"Lists the items the player currently has.", "Lists the items the player currently has.", "Lists the items the player currently has.", "Enumera los objetos que el jugador tiene actualmente.", "Lists the items the player currently has.", "Lists the items the player currently has.", "현재 캐릭터가 가진 아이템 목록을 출력합니다.", "输出本局角色目前持有的道具。"}},
    {{"Locks achievements", "Locks achievements", "Locks achievements", "Bloquea los logros", "Locks achievements", "Locks achievements", "도전 과제 잠금", "锁定成就"}},
    {{"Runs the given Lua code immediately. Anything which would work in a standard file will work here.\nThis command also has shorthand which is just (l).", "Runs the given Lua code immediately. Anything which would work in a standard file will work here.\nThis command also has shorthand which is just (l).", "Runs the given Lua code immediately. Anything which would work in a standard file will work here.\nThis command also has shorthand which is just (l).", "Ejecuta el codigo Lua dado inmediatamente. Cualquier cosa que funcione en un archivo estándar funcionará aquí.\nEste comando también tiene una abreviatura (l).", "Runs the given Lua code immediately. Anything which would work in a standard file will work here.\nThis command also has shorthand which is just (l).", "Runs the given Lua code immediately. Anything which would work in a standard file will work here.\nThis command also has shorthand which is just (l).", "작성한 Lua 코드를 즉시 실행합니다. 일반 Lua 파일에서 작동하는 코드는 모두 여기에서도 사용할 수 있습니다.\n이 명령어의 약자는 (l)입니다.", "立即运行输入的Lua代码。任何可以在Lua文件中运行的代码都可以在此处运行。\n这个命令的缩写是（l）"}},
    {{"Displays the currently used RAM of LUA.", "Displays the currently used RAM of LUA.", "Displays the currently used RAM of LUA.", "Muestra la RAM utilizada actualmente por LUA.", "Displays the currently used RAM of LUA.", "Displays the currently used RAM of LUA.", "Lua에서 현재 사용 중인 RAM을 표시합니다.", "显示出当前Lua使用的内存空间用量"}},
    {{"Reloads Lua code for the given mod folder.\nExample:\n(luamod testmod) will reload Lua code for the mod in the folder \"testmod\".", "Reloads Lua code for the given mod folder.\nExample:\n(luamod testmod) will reload Lua code for the mod in the folder \"testmod\".", "Reloads Lua code for the given mod folder.\nExample:\n(luamod testmod) will reload Lua code for the mod in the folder \"testmod\".", "Recarga el codigo Lua de la carpeta de mod especificada.\nEjemplo:\n(luamod testmod) recargará el codigo Lua para el mod en la carpeta \"testmod\".", "Reloads Lua code for the given mod folder.\nExample:\n(luamod testmod) will reload Lua code for the mod in the folder \"testmod\".", "Reloads Lua code for the given mod folder.\nExample:\n(luamod testmod) will reload Lua code for the mod in the folder \"testmod\".", "지정한 모드 폴더의 Lua 코드를 다시 불러옵니다.\n예시:\n(luamod testmod)를 입력하면 \"testmod\" 폴더에 있는 Lua 코드를 다시 불러옵니다.", "重新加载选定mod文件夹中的Lua代码。\n例如：\n（luamod testmod）会重新加载文件夹\"testmod\"内的Lua代码。"}},
    {{"Destroys the current Lua context and recreates it from scratch. This is mostly a backend command meant to help sync up networked play.\nThis has Unforeseen Consequences if done in-game, please only do this on the menu unless you know what you're doing. Please\?", "Destroys the current Lua context and recreates it from scratch. This is mostly a backend command meant to help sync up networked play.\nThis has Unforeseen Consequences if done in-game, please only do this on the menu unless you know what you're doing. Please\?", "Destroys the current Lua context and recreates it from scratch. This is mostly a backend command meant to help sync up networked play.\nThis has Unforeseen Consequences if done in-game, please only do this on the menu unless you know what you're doing. Please\?", "Destruye el contexto Lua actual y lo recrea desde cero. Este es esencialmente un comando de backend para ayudar a sincronizar el juego en red.\nEste tiene Consecuencias Imprevistas al ejecutarse in-game, Por favor solo usalo en el menu a menos que sepas lo que haces. Plis\?", "Destroys the current Lua context and recreates it from scratch. This is mostly a backend command meant to help sync up networked play.\nThis has Unforeseen Consequences if done in-game, please only do this on the menu unless you know what you're doing. Please\?", "Destroys the current Lua context and recreates it from scratch. This is mostly a backend command meant to help sync up networked play.\nThis has Unforeseen Consequences if done in-game, please only do this on the menu unless you know what you're doing. Please\?", "현재 Lua 컨텍스트를 제거하고 새로 생성합니다. 이 명령어는 주로 네트워크 플레이 동기화를 위한 백엔드용 명령어입니다.\n인게임에서 실행 시 예기치 못한 문제가 발생할 수 있으니, 메뉴 화면에서만 사용하세요. 특히 이 명령어의 영향을 완전히 이해하지 못했다면 더욱이요. 부탁드립니다.", "销毁当前的Lua上下文并重新创建。这主要是一个后端命令，以帮助同步在线游戏。\n如果在游戏中这样做，将产生不可预见的后果，请只在主菜单上使用此命令，除非你知道自己在做什么。拜托？"}},
    {{"Runs a given Lua file immediately.\nExample:\n(luarun mods/test/test.lua) would run \"test.lua\" inside the \"test\" mod folder.", "Runs a given Lua file immediately.\nExample:\n(luarun mods/test/test.lua) would run \"test.lua\" inside the \"test\" mod folder.", "Runs a given Lua file immediately.\nExample:\n(luarun mods/test/test.lua) would run \"test.lua\" inside the \"test\" mod folder.", "Ejecuta el archivo Lua dado inmediatamente.\nEjemplo:\n(luarun mods/test/test.lua) ejecutará \"test.lua\" dentro de la carpeta del mod \"test\".", "Runs a given Lua file immediately.\nExample:\n(luarun mods/test/test.lua) would run \"test.lua\" inside the \"test\" mod folder.", "Runs a given Lua file immediately.\nExample:\n(luarun mods/test/test.lua) would run \"test.lua\" inside the \"test\" mod folder.", "지정한 Lua 파일을 즉시 실행합니다.\n예시:\n(luarun mods/test/test.lua)을 입력하면 \"test\" 모드 폴더의 \"test.lua\"를 실행합니다.", "立即运行选定的Lua文件\n例如：\n（luarun mods/test/test.lua）将运行“test”模组文件夹中的“test.lua”。"}},
    {{"Run a set of commands in a specified order. These are effectively shortcuts. Refer to autocomplete for a list of macro commands.", "Run a set of commands in a specified order. These are effectively shortcuts. Refer to autocomplete for a list of macro commands.", "Run a set of commands in a specified order. These are effectively shortcuts. Refer to autocomplete for a list of macro commands.", "Activa un conjunto de comandos en el orden especifcado. Son, basicamente, accesos directos. Consulte el autocompletado para obtener una lista de comandos macro.", "Run a set of commands in a specified order. These are effectively shortcuts. Refer to autocomplete for a list of macro commands.", "Run a set of commands in a specified order. These are effectively shortcuts. Refer to autocomplete for a list of macro commands.", "여러 명령어를 순서대로 실행합니다. 일종의 단축키입니다. 매크로는 자동 완성 기능에서 확인할 수 있습니다.", "按指定的顺序执行命令。请查看自动补全获取宏命令表，这些命令可以提高效率。"}},
    {{"Overrides the next item Metronome will become.\nExample:\n(metro c1) will force Metronome to become The Sad Onion.", "Overrides the next item Metronome will become.\nExample:\n(metro c1) will force Metronome to become The Sad Onion.", "Overrides the next item Metronome will become.\nExample:\n(metro c1) will force Metronome to become The Sad Onion.", "Anula el proximo objeto que utilizaría el Metronomo.\nEjemplo:\n(metro c1) obligará a Metronomo a convertirse en Sad Onion.", "Overrides the next item Metronome will become.\nExample:\n(metro c1) will force Metronome to become The Sad Onion.", "Overrides the next item Metronome will become.\nExample:\n(metro c1) will force Metronome to become The Sad Onion.", "메트로놈이 다음에 발동할 아이템을 설정합니다.\n예시:\n(metro c1)을 입력하면 메트로놈을 사용했을 때 눈물나는 양파의 효과가 발동됩니다.", "规定节拍器所生成的下个道具。\n例如：\n（metro c1）将强制节拍器给予悲伤洋葱。"}},
    {{"Changes network delay to a specified value. Can be useful if you see stutters during online gameplay.", "Changes network delay to a specified value. Can be useful if you see stutters during online gameplay.", "Changes network delay to a specified value. Can be useful if you see stutters during online gameplay.", "Cambia la latencia de red a un valor especifico. Puede ser util si notas cortes al jugar en linea.", "Changes network delay to a specified value. Can be useful if you see stutters during online gameplay.", "Changes network delay to a specified value. Can be useful if you see stutters during online gameplay.", "지정한 값으로 네트워크 지연 시간을 변경합니다. 온라인 플레이 중 끊김 현상에 도움이 될 수 있습니다.", "将网络延迟设置为选定值。如果在联机游戏中遭遇闪回可以使用。"}},
    {{"Connects player(s) with specified Steam ID to your game (online multiplayer). Allows up to 4 players.\nExample:\nnetstart <steam_user_id1> <steam_user_id2>", "Connects player(s) with specified Steam ID to your game (online multiplayer). Allows up to 4 players.\nExample:\nnetstart <steam_user_id1> <steam_user_id2>", "Connects player(s) with specified Steam ID to your game (online multiplayer). Allows up to 4 players.\nExample:\nnetstart <steam_user_id1> <steam_user_id2>", "Conecta jugador(es) con la Steam ID especificada a tu juego (multijugador online). Permite hasta 4 jugadores.\nEjemplo:\nnetstart <steam_user_id1> <steam_user_id2>", "Connects player(s) with specified Steam ID to your game (online multiplayer). Allows up to 4 players.\nExample:\nnetstart <steam_user_id1> <steam_user_id2>", "Connects player(s) with specified Steam ID to your game (online multiplayer). Allows up to 4 players.\nExample:\nnetstart <steam_user_id1> <steam_user_id2>", "지정한 Steam ID와 연결합니다. (온라인 멀티플레이) 최대 4인까지 가능합니다.\n예시:\nnetstart <steam_user_id1> <steam_user_id2>", "与选定Steam ID的玩家进行链接（在线多人）。最多四名玩家。\n例如：\nnetstart <steam_user_id1> <steam_user_id2>"}},
    {{"Plays a sound effect immediately.\nExample:\n(playsfx 187) will play an incorrect buzzer.", "Plays a sound effect immediately.\nExample:\n(playsfx 187) will play an incorrect buzzer.", "Plays a sound effect immediately.\nExample:\n(playsfx 187) will play an incorrect buzzer.", "Reproduce un efecto de sonido inmediatamente.\nEjemplo:\n(playsfx 187) reproducirá un boton de incorrecto.", "Plays a sound effect immediately.\nExample:\n(playsfx 187) will play an incorrect buzzer.", "Plays a sound effect immediately.\nExample:\n(playsfx 187) will play an incorrect buzzer.", "지정한 효과음을 즉시 재생합니다.\n예시:\n(playsfx 187)을 입력하면 incorrect 버저음을 재생합니다.", "立即播放游戏内的音效。\n例如：\n（playsfx 187）会播放错误提示。"}},
    {{"Supposed to log information to a CSV. Blame Nicalis!", "Supposed to log information to a CSV. Blame Nicalis!", "Supposed to log information to a CSV. Blame Nicalis!", "Supuestamente almacena informacion en un CSV. Culpa a Nicalis!", "Supposed to log information to a CSV. Blame Nicalis!", "Supposed to log information to a CSV. Blame Nicalis!", "원래라면 CSV로 정보 로그를 남겨야 합니다. Nicalis 때문이에요!", "本应收集数据并写入csv文件的，但无法使用。都怪Nicalis！"}},
    {{"Supposed to stop profiling but profiling is broken because we can't have nice things.", "Supposed to stop profiling but profiling is broken because we can't have nice things.", "Supposed to stop profiling but profiling is broken because we can't have nice things.", "Supuestamente deberia detener profiling pero profiling no funciona porque no podemos tener cosas bonitas.", "Supposed to stop profiling but profiling is broken because we can't have nice things.", "Supposed to stop profiling but profiling is broken because we can't have nice things.", "데이터 추적을 중단해야 하는데, 추적 기능 자체가 고장 났습니다. 좋은 걸 가질 수 없는 운명이죠.", "本应停止收集数据的，但采集功能是坏的，全都是因为Nicalis太粗心了！"}},
    {{"Removes an item from the player immediately. Accepts the same syntax as give, look at that command's help for more info.", "Removes an item from the player immediately. Accepts the same syntax as give, look at that command's help for more info.", "Removes an item from the player immediately. Accepts the same syntax as give, look at that command's help for more info.", "Remueve un objeto del jugador inmediatamente. Acepta la misma sintaxis que \"give\", revisar la ayuda de ese comando para mas información.", "Removes an item from the player immediately. Accepts the same syntax as give, look at that command's help for more info.", "Removes an item from the player immediately. Accepts the same syntax as give, look at that command's help for more info.", "캐릭터에게서 아이템을 즉시 제거합니다. 사용법은 give 명령어와 동일하니, 자세한 내용은 해당 도움말을 참조하세요.", "立即移除角色的物品。输入规则与give相同，查看give命令的帮助以获取更多信息。"}},
    {{"Removes an item from the second player immediately. Accepts the same syntax as give, look at that command's help for more info.", "Removes an item from the second player immediately. Accepts the same syntax as give, look at that command's help for more info.", "Removes an item from the second player immediately. Accepts the same syntax as give, look at that command's help for more info.", "Remueve un objeto del segundo jugador inmediatamente. Acepta la misma sintaxis que \"give\", revisar la ayuda de ese comando para mas información.", "Removes an item from the second player immediately. Accepts the same syntax as give, look at that command's help for more info.", "Removes an item from the second player immediately. Accepts the same syntax as give, look at that command's help for more info.", "2번째 캐릭터에게서 아이템을 즉시 제거합니다. 사용법은 give 명령어와 동일하니, 자세한 내용은 해당 도움말을 참조하세요.", "立即移除第二角色的物品。输入规则与give相同，查看give命令的帮助以获取更多信息。"}},
    {{"Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re).", "Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re).", "Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re).", "Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re).", "Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re).", "Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re).", "Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re).", "Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re)."}},
    {{"Reloads the current floor's effects.", "Reloads the current floor's effects.", "Reloads the current floor's effects.", "Recarga la capa de efectos visuales del piso actual.", "Reloads the current floor's effects.", "Reloads the current floor's effects.", "현재 층의 시각 효과 다시 불러옵니다.", "重载当前楼层的特效渲染图层。"}},
    {{"Reloads any currently loaded shaders.", "Reloads any currently loaded shaders.", "Reloads any currently loaded shaders.", "Recarga todo sombreador(shader) cargado actualmente.", "Reloads any currently loaded shaders.", "Reloads any currently loaded shaders.", "현재 불러온 모든 셰이더를 다시 불러옵니다.", "重载全部已加载的光影。"}},
    {{"Reloads wisps spawned by Book of Virtues and locusts spawned by Abyss.", "Reloads wisps spawned by Book of Virtues and locusts spawned by Abyss.", "Reloads wisps spawned by Book of Virtues and locusts spawned by Abyss.", "Recarga los fuegos fatuos generados por Libro de virtudes y langostas generadas por Abismo.", "Reloads wisps spawned by Book of Virtues and locusts spawned by Abyss.", "Reloads wisps spawned by Book of Virtues and locusts spawned by Abyss.", "미덕의 서의 위습과 무저갱의 메뚜기를 다시 불러옵니다.", "重新加载美德之书生成的魂火跟班和无底坑生成的蝗虫。"}},
    {{"Repeats the previously entered command X amount of times.\nExample:\n(giveitem 1) is used to give the player The Sad Onion. (repeat 5) is then used to give the player The Sad Onion five more times.", "Repeats the previously entered command X amount of times.\nExample:\n(giveitem 1) is used to give the player The Sad Onion. (repeat 5) is then used to give the player The Sad Onion five more times.", "Repeats the previously entered command X amount of times.\nExample:\n(giveitem 1) is used to give the player The Sad Onion. (repeat 5) is then used to give the player The Sad Onion five more times.", "Repite el comando ingresado previamente X cantidad de veces.\nEjemplo:\n(giveitem 1) es usado para darle al jugador \"Sad Onion\". (repeat 5) es usado para darle al jugador \"Sad Onion\" cinco veces mas.", "Repeats the previously entered command X amount of times.\nExample:\n(giveitem 1) is used to give the player The Sad Onion. (repeat 5) is then used to give the player The Sad Onion five more times.", "Repeats the previously entered command X amount of times.\nExample:\n(giveitem 1) is used to give the player The Sad Onion. (repeat 5) is then used to give the player The Sad Onion five more times.", "직전에 입력한 명령어를 지정한 횟수만큼 반복합니다.\n예시:\n(giveitem 1)을 입력하면 캐릭터에게 눈물나는 양파를 지급하고, 그 후로 (repeat 5)을 입력하면 추가로 5개 더 지급합니다.", "将上一条输入的命令重复X次\n例如：\n（giveitem 1）会给予角色悲伤洋葱。（repeat 5）将再重复给予角色五次悲伤洋葱。"}},
    {{"Reseeds the current floor, generating a brand new layout for it.", "Reseeds the current floor, generating a brand new layout for it.", "Reseeds the current floor, generating a brand new layout for it.", "Reinicia el piso actual, generando un nuevo diseño.", "Reseeds the current floor, generating a brand new layout for it.", "Reseeds the current floor, generating a brand new layout for it.", "현재 층을 무작위 시드로 교체하여 새로운 방 배치를 생성합니다.", "使用随机种子替换当前层的房间分布，会生成新的房间布局。"}},
    {{"Restarts the game on a new run. Accepts an optional argument which is the character ID.\nExample:\n(restart 3) starts a new run as Judas.", "Restarts the game on a new run. Accepts an optional argument which is the character ID.\nExample:\n(restart 3) starts a new run as Judas.", "Restarts the game on a new run. Accepts an optional argument which is the character ID.\nExample:\n(restart 3) starts a new run as Judas.", "Reinicia el juego en una nueva partida. Opcionalmente permite elegir un personaje especifico con su ID.\nEjemplo:\n(restart 3) inicia una nueva partida como Judas.", "Restarts the game on a new run. Accepts an optional argument which is the character ID.\nExample:\n(restart 3) starts a new run as Judas.", "Restarts the game on a new run. Accepts an optional argument which is the character ID.\nExample:\n(restart 3) starts a new run as Judas.", "새 게임을 시작합니다. (선택)매개변수로 새로 시작할 캐릭터 ID를 지정할 수 있습니다.\n예시:\n(restart 3)을 입력하면 유다로 새 게임을 시작합니다.", "重新开始一局新的游戏。接受角色ID作为可选参数。\n例如：\n（restart 3）会以犹大开始新的一局游戏。"}},
    {{"Restocks all shops.", "Restocks all shops.", "Restocks all shops.", "Reabastece todas las tiendas.", "Restocks all shops.", "Restocks all shops.", "모든 상점을 재입고합니다.", "补充所有商店。"}},
    {{"Makes the game forget about the changes in current room and teleports Isaac back to previous room. Can be used to fix desynchronization issues if you use this command in a room where it happened. (Glowing Hourglass-like effect)", "Makes the game forget about the changes in current room and teleports Isaac back to previous room. Can be used to fix desynchronization issues if you use this command in a room where it happened. (Glowing Hourglass-like effect)", "Makes the game forget about the changes in current room and teleports Isaac back to previous room. Can be used to fix desynchronization issues if you use this command in a room where it happened. (Glowing Hourglass-like effect)", "Hace que el juego olvide los cambios en la sala actual y teletransporta a Isaac a la sala anterior. Puede utilizarse para solucionar problemas de sincronización si se usa este comando en la sala donde sucedio. (Efecto similar al \"Glowing Hour Glass\")", "Makes the game forget about the changes in current room and teleports Isaac back to previous room. Can be used to fix desynchronization issues if you use this command in a room where it happened. (Glowing Hourglass-like effect)", "Makes the game forget about the changes in current room and teleports Isaac back to previous room. Can be used to fix desynchronization issues if you use this command in a room where it happened. (Glowing Hourglass-like effect)", "현재 방에서의 모든 변화를 무시하고 게임을 이전 방으로 되돌립니다. 동기화 오류가 발생한 방에서 오류를 해결할 수 있습니다. (빛나는 모래시계 효과와 유사)", "取消当前房间中产生的所有变化传送回上一个房间。在出现同步失效的房间使用可修复同步失效。（类似发光沙漏）"}},
    {{"Starts a new run with the given seed.\nExample:\n(seed N1CA L1SY) will start a new run with the seed N1CA L1SY.", "Starts a new run with the given seed.\nExample:\n(seed N1CA L1SY) will start a new run with the seed N1CA L1SY.", "Starts a new run with the given seed.\nExample:\n(seed N1CA L1SY) will start a new run with the seed N1CA L1SY.", "Inicia una nueva partida con la semilla establecida.\nEjemplo:\n(seed N1CA L1SY) Iniciará una nueva partida con la semilla N1CA L1SY.", "Starts a new run with the given seed.\nExample:\n(seed N1CA L1SY) will start a new run with the seed N1CA L1SY.", "Starts a new run with the given seed.\nExample:\n(seed N1CA L1SY) will start a new run with the seed N1CA L1SY.", "지정한 시르도 새 게임을 시작합니다.\n예시:\n(seed N1CA L1SY)을 입력하면 N1CA L1SY 시드로 새 게임을 시작합니다.", "使用选定种子重新开始一局新的游戏。\n例如：\n（seed N1CA L1SY）将以种子N1CA L1SY开始一局新的游戏。"}},
    {{"Spawns a new entity. Syntax is (type).(variant).(subtype).(champion).\nExample:\n(spawn 5.40.1) will spawn a bomb.", "Spawns a new entity. Syntax is (type).(variant).(subtype).(champion).\nExample:\n(spawn 5.40.1) will spawn a bomb.", "Spawns a new entity. Syntax is (type).(variant).(subtype).(champion).\nExample:\n(spawn 5.40.1) will spawn a bomb.", "Invoca una nueva entidad. La sintaxis es (tipo).(variante).(subtipo).(campeon).\nEjemplo:\n(spawn 5.40.1) invocará una bomba.", "Spawns a new entity. Syntax is (type).(variant).(subtype).(champion).\nExample:\n(spawn 5.40.1) will spawn a bomb.", "Spawns a new entity. Syntax is (type).(variant).(subtype).(champion).\nExample:\n(spawn 5.40.1) will spawn a bomb.", "새 엔티티를 생성합니다. 문법은 (type).(variant).(subtype).(champion)입니다.\n예시:\n(spawn 5.40.1)을 입력하면 폭탄을 생성합니다.", "生成一个新的实体。参数为(type).(variant).(subtype).(champion)。\n例如：\n（spawn 5.40.1）会生成一个炸弹。"}},
    {{"Immediately goes to the specified stage. Accepts (a-d) as modifiers, with (a) corresponding to WOTL alts, (b) corresponding to Afterbirth alts, (c) corresponding to Antibirth alts, and (d) corresponding to Repentance alts.\nExample:\n(stage 4d) will take the player to Ashpit II.", "Immediately goes to the specified stage. Accepts (a-d) as modifiers, with (a) corresponding to WOTL alts, (b) corresponding to Afterbirth alts, (c) corresponding to Antibirth alts, and (d) corresponding to Repentance alts.\nExample:\n(stage 4d) will take the player to Ashpit II.", "Immediately goes to the specified stage. Accepts (a-d) as modifiers, with (a) corresponding to WOTL alts, (b) corresponding to Afterbirth alts, (c) corresponding to Antibirth alts, and (d) corresponding to Repentance alts.\nExample:\n(stage 4d) will take the player to Ashpit II.", "Te envia inmediatamente al escenario especificado. Acepta (a-d) como modificadores, donde (a) corresponde a rutas alt de WOTL, (b) coresponde a rutas alt de Afterbirth, (c) corresponde a rutas alt de Antibirth, y (d) corresponde a rutas alt de Repentance.\nEjemplo:\n(stage 4d) enviará al jugador a Ashpit II.", "Immediately goes to the specified stage. Accepts (a-d) as modifiers, with (a) corresponding to WOTL alts, (b) corresponding to Afterbirth alts, (c) corresponding to Antibirth alts, and (d) corresponding to Repentance alts.\nExample:\n(stage 4d) will take the player to Ashpit II.", "Immediately goes to the specified stage. Accepts (a-d) as modifiers, with (a) corresponding to WOTL alts, (b) corresponding to Afterbirth alts, (c) corresponding to Antibirth alts, and (d) corresponding to Repentance alts.\nExample:\n(stage 4d) will take the player to Ashpit II.", "지정한 스테이지로 즉시 이동합니다. (a~d)를 수정자로 사용하며, (a)는 어린 양의 분노, (b)는 애프터버스, (c)는 안티버스, (d)는 리펜턴스에서의 변형 스테이지를 의미합니다..\n예시:\n(stage 4d)을 입력하면 잿구덩이 II로 이동합니다.", "立即传送至特定章节与楼层。使用（a-d）作为修饰符，（a）对应羔羊的愤怒变种，（b）对应胎衣变种，（c）对应抗生变种，（d）对应忏悔变种。\n例如：\n（stage 4d）将角色传送至淹水洞穴II。"}},
    {{"Prints the total amount of time passed on the run.", "Prints the total amount of time passed on the run.", "Prints the total amount of time passed on the run.", "Imprime en la consola la cantidad total de tiempo en la partida.", "Prints the total amount of time passed on the run.", "Prints the total amount of time passed on the run.", "현재 게임에서 경과한 총 시간을 출력합니다.", "输出本局游戏经过的时间。"}},
    {{"Prints a list of boss names and percentage chance (100%=10000) for current floor.", "Prints a list of boss names and percentage chance (100%=10000) for current floor.", "Prints a list of boss names and percentage chance (100%=10000) for current floor.", "Imprime en la consola una lista de nombres de jefes y porcentajes (100%=10000) para el piso actual.", "Prints a list of boss names and percentage chance (100%=10000) for current floor.", "Prints a list of boss names and percentage chance (100%=10000) for current floor.", "현재 층의 보스 이름과 등장 확률(100%=10000)을 출력합니다.", "输出当前层头目的名称与概率，概率以百分数形式表示（100%=10000）。"}},
};

inline constexpr ConsoleBuiltinCommandMetadata kConsoleBuiltinCommandMetadata[] = {
    {"achievement", "", "Unlocks achievements", "Unlocks achievements", &kConsoleBuiltinCommandLocalizedDescriptions[0], &kConsoleBuiltinCommandLocalizedHelpTexts[0], true, ConsoleAutocompleteType::Achievement},
    {"addplayer", "", "Spawns a new player", "Spawns a new player entity. On default, it spawns Isaac with controller ID 0.\nPlayer ID -1 lets you take control of a random enemy in the room.\nExample:\n(addplayer 7 1) Spawns Azazel and can be controlled with the second input device (controller 1 in most cases)", &kConsoleBuiltinCommandLocalizedDescriptions[1], &kConsoleBuiltinCommandLocalizedHelpTexts[1], false, ConsoleAutocompleteType::Player},
    {"challenge", "", "Start a challenge run", "Stops the current run and starts a new run on a random seed with the given challenge ID.\nExample:\n(challenge 20) will start a new Purist challenge run.\n", &kConsoleBuiltinCommandLocalizedDescriptions[2], &kConsoleBuiltinCommandLocalizedHelpTexts[2], false, ConsoleAutocompleteType::Challenge},
    {"cleanbestiary", "", "Clear unneeded bestiary data to reduce save file size", "Clears bestiary data (encounters, kills etc) from the current save file for any enemy that cannot appear in the bestiary, or does not currently exist (ie, an enemy from a mod that is not currently enabled). Only useful if your save file is nearing the breaking point of 64KB (difficult, but possible).", &kConsoleBuiltinCommandLocalizedDescriptions[3], &kConsoleBuiltinCommandLocalizedHelpTexts[3], true, ConsoleAutocompleteType::None},
    {"clear", "", "Clear the debug console", "Clears all text currently displayed in the debug console. Only the line \"Repentance Console\" will remain.", &kConsoleBuiltinCommandLocalizedDescriptions[4], &kConsoleBuiltinCommandLocalizedHelpTexts[4], true, ConsoleAutocompleteType::None},
    {"clearcache", "", "Clear the sprite cache", "Clears the game's sprite cache. This can be useful for trying to deal with memory issues.\nThis also has the side effect of reloading modded sprites without needing a full game restart.", &kConsoleBuiltinCommandLocalizedDescriptions[5], &kConsoleBuiltinCommandLocalizedHelpTexts[5], true, ConsoleAutocompleteType::None},
    {"clearseeds", "", "Clear easter egg seeds in the current run", "Clears any \"special\" seed effects in the current run.\nExample:\nThe seed effect GFVE LLLL is applied in a run. Running clearseeds will remove this effect.", &kConsoleBuiltinCommandLocalizedDescriptions[6], &kConsoleBuiltinCommandLocalizedHelpTexts[6], false, ConsoleAutocompleteType::None},
    {"combo", "", "Give items from a specified pool", "Gives a specified number of items from a specified item pool.\nExample:\n(combo 4.6) will give six random items from the Angel item pool.\nNo, I don't know why they made a bespoke ID system for this one (1) command.", &kConsoleBuiltinCommandLocalizedDescriptions[7], &kConsoleBuiltinCommandLocalizedHelpTexts[7], false, ConsoleAutocompleteType::Combo},
    {"copy", "", "Copy previous commands to clipboard", "Copies a specified amount of previous console commands to the system clipboard.\nExample:\n(copy 3) will copy the previous three commands.", &kConsoleBuiltinCommandLocalizedDescriptions[8], &kConsoleBuiltinCommandLocalizedHelpTexts[8], true, ConsoleAutocompleteType::None},
    {"costumetest", "", "Give the player random costumes", "Gives the player a specified amount of random costumes.\nExample:\n(costumetest 34) will give the player 34 random costumes.", &kConsoleBuiltinCommandLocalizedDescriptions[9], &kConsoleBuiltinCommandLocalizedHelpTexts[9], false, ConsoleAutocompleteType::None},
    {"curse", "", "Add curses to the current run", "Permanently (until overridden) adds curses to the run. This command uses a bitmask- the curse with an ID of 1 is 1, 2 is 2, 3 is 4, 4 is 8, and so on. In this manner, desired curse ID's are tallied up and multiple can be enabled simultaneously.\nExample:\n(curse 96) will enable Curse of the Blind and Curse of the Maze simultaneously.", &kConsoleBuiltinCommandLocalizedDescriptions[10], &kConsoleBuiltinCommandLocalizedHelpTexts[10], true, ConsoleAutocompleteType::Curse},
    {"cutscene", "", "Play a cutscene", "Immediately plays the specified cutscenne.\nExample:\n(cutscene 1) will immediately play the game's intro.", &kConsoleBuiltinCommandLocalizedDescriptions[11], &kConsoleBuiltinCommandLocalizedHelpTexts[11], true, ConsoleAutocompleteType::Cutscene},
    {"debug", "", "Enable a debug flag", "Enables the specified debug flag.\nExample:\n(debug 3) will grant the player infinite HP.", &kConsoleBuiltinCommandLocalizedDescriptions[12], &kConsoleBuiltinCommandLocalizedHelpTexts[12], false, ConsoleAutocompleteType::DebugFlag},
    {"delirious", "", "Force Delirious to be a certain boss", "Overrides the next boss the Delirious item will become.\nExample:\n(delirious 3) will force Delirious to be a Chub.", &kConsoleBuiltinCommandLocalizedDescriptions[13], &kConsoleBuiltinCommandLocalizedHelpTexts[13], false, ConsoleAutocompleteType::Delirious},
    {"eggs", "", "Unlock all easter egg seeds", "PERMANENTLY unlocks all easter eggs in this save file.", &kConsoleBuiltinCommandLocalizedDescriptions[14], &kConsoleBuiltinCommandLocalizedHelpTexts[14], true, ConsoleAutocompleteType::None},
    {"forceroom", "", "Force a room to be used in level generator", "Allows to set any room as \"forced room\". Said room gets weight of 1000, making it more likely to appear on floor with reseed command.", &kConsoleBuiltinCommandLocalizedDescriptions[15], &kConsoleBuiltinCommandLocalizedHelpTexts[15], false, ConsoleAutocompleteType::Goto},
    {"fullrestart", "", "Closes and reopens the game", "Closes and reopens the game", &kConsoleBuiltinCommandLocalizedDescriptions[16], &kConsoleBuiltinCommandLocalizedHelpTexts[16], true, ConsoleAutocompleteType::None},
    {"giveeffect", "ge", "Give the character a TemporaryEffect", "Gives the main player TemporaryEffects, by ID or name. Grants the effect of Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (ge).\nExamples:\n(giveeffect 74) will give the player Luna's tears up Null Item.\n(giveeffect c34) will give the player Book of Belial's damage up effect.", &kConsoleBuiltinCommandLocalizedDescriptions[17], &kConsoleBuiltinCommandLocalizedHelpTexts[17], false, ConsoleAutocompleteType::Effect},
    {"giveitem", "g", "Give the character items, trinkets, cards, and pills", "Gives the main player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem c1) will give the player The Sad Onion.\n(giveitem t1) will give the player Gulp!\n(giveitem p1) will give the player a Bad Trip pill.\n(giveitem k1) will give the player 0 - The Fool.", &kConsoleBuiltinCommandLocalizedDescriptions[18], &kConsoleBuiltinCommandLocalizedHelpTexts[18], false, ConsoleAutocompleteType::Item},
    {"giveitem2", "g2", "Give player 2 items, trinkets, cards, and pills", "Gives the second player items, trinkets, cards and pills. These can either be by name or by prefix. Prefixes are (c) for items, (t) for trinkets, (T) for golden trinkets, (p) for pills, (P) for horse pills, and (k) for cards. Most pocket items count as cards.\nThis command also has shorthand which is just (g).\nExamples:\n(giveitem2 c1) will give the player The Sad Onion.\n(giveitem2 t1) will give the player Gulp!\n(giveitem2 p1) will give the player a Bad Trip pill.\n(giveitem2 k1) will give the player 0 - The Fool.", &kConsoleBuiltinCommandLocalizedDescriptions[19], &kConsoleBuiltinCommandLocalizedHelpTexts[19], false, ConsoleAutocompleteType::Item},
    {"goto", "", "Teleport to a new room", "Teleports the character to a new room. Use (d) for a standard room, (s) for a special room, or three numbers to teleport to an existing room on the floor.\nExample:\n(goto s.boss.1010) will go to a Monstro fight.", &kConsoleBuiltinCommandLocalizedDescriptions[20], &kConsoleBuiltinCommandLocalizedHelpTexts[20], false, ConsoleAutocompleteType::Goto},
    {"gridspawn", "", "Spawn a grid entity", "Spawns a new grid entity of the given ID at a random place in the room.", &kConsoleBuiltinCommandLocalizedDescriptions[21], &kConsoleBuiltinCommandLocalizedHelpTexts[21], false, ConsoleAutocompleteType::Grid},
    {"help", "", "Get info about commands", "Retrieve further info about a command and its syntax.", &kConsoleBuiltinCommandLocalizedDescriptions[22], &kConsoleBuiltinCommandLocalizedHelpTexts[22], true, ConsoleAutocompleteType::None},
    {"listcollectibles", "", "List current items", "Lists the items the player currently has.", &kConsoleBuiltinCommandLocalizedDescriptions[23], &kConsoleBuiltinCommandLocalizedHelpTexts[23], false, ConsoleAutocompleteType::None},
    {"lockachievement", "", "Locks achievements", "Locks achievements", &kConsoleBuiltinCommandLocalizedDescriptions[24], &kConsoleBuiltinCommandLocalizedHelpTexts[24], true, ConsoleAutocompleteType::Achievement},
    {"lua", "", "Run Lua code", "Runs the given Lua code immediately. Anything which would work in a standard file will work here.\nThis command also has shorthand which is just (l).", &kConsoleBuiltinCommandLocalizedDescriptions[25], &kConsoleBuiltinCommandLocalizedHelpTexts[25], true, ConsoleAutocompleteType::None},
    {"luamem", "", "Display lua memory usage", "Displays the currently used RAM of LUA.", &kConsoleBuiltinCommandLocalizedDescriptions[26], &kConsoleBuiltinCommandLocalizedHelpTexts[26], true, ConsoleAutocompleteType::None},
    {"luamod", "", "Reload a Lua mod", "Reloads Lua code for the given mod folder.\nExample:\n(luamod testmod) will reload Lua code for the mod in the folder \"testmod\".", &kConsoleBuiltinCommandLocalizedDescriptions[27], &kConsoleBuiltinCommandLocalizedHelpTexts[27], true, ConsoleAutocompleteType::ModFolder},
    {"luareset", "", "[EXPERIMENTAL] Reset the Lua context", "Destroys the current Lua context and recreates it from scratch. This is mostly a backend command meant to help sync up networked play.\nThis has Unforeseen Consequences if done in-game, please only do this on the menu unless you know what you're doing. Please\?", &kConsoleBuiltinCommandLocalizedDescriptions[28], &kConsoleBuiltinCommandLocalizedHelpTexts[28], true, ConsoleAutocompleteType::None},
    {"luarun", "", "Run a Lua file", "Runs a given Lua file immediately.\nExample:\n(luarun mods/test/test.lua) would run \"test.lua\" inside the \"test\" mod folder.", &kConsoleBuiltinCommandLocalizedDescriptions[29], &kConsoleBuiltinCommandLocalizedHelpTexts[29], true, ConsoleAutocompleteType::None},
    {"macro", "m", "Trigger a set of commands", "Run a set of commands in a specified order. These are effectively shortcuts. Refer to autocomplete for a list of macro commands.", &kConsoleBuiltinCommandLocalizedDescriptions[30], &kConsoleBuiltinCommandLocalizedHelpTexts[30], false, ConsoleAutocompleteType::Macro},
    {"metro", "", "Force Metronome to be a certain item", "Overrides the next item Metronome will become.\nExample:\n(metro c1) will force Metronome to become The Sad Onion.", &kConsoleBuiltinCommandLocalizedDescriptions[31], &kConsoleBuiltinCommandLocalizedHelpTexts[31], false, ConsoleAutocompleteType::Metro},
    {"netdelay", "", "Change network delay", "Changes network delay to a specified value. Can be useful if you see stutters during online gameplay.", &kConsoleBuiltinCommandLocalizedDescriptions[32], &kConsoleBuiltinCommandLocalizedHelpTexts[32], true, ConsoleAutocompleteType::None},
    {"netstart", "", "Initialize online coop", "Connects player(s) with specified Steam ID to your game (online multiplayer). Allows up to 4 players.\nExample:\nnetstart <steam_user_id1> <steam_user_id2>", &kConsoleBuiltinCommandLocalizedDescriptions[33], &kConsoleBuiltinCommandLocalizedHelpTexts[33], true, ConsoleAutocompleteType::None},
    {"playsfx", "", "Play a sound effect", "Plays a sound effect immediately.\nExample:\n(playsfx 187) will play an incorrect buzzer.", &kConsoleBuiltinCommandLocalizedDescriptions[34], &kConsoleBuiltinCommandLocalizedHelpTexts[34], true, ConsoleAutocompleteType::Sfx},
    {"prof", "", "[BROKEN] Start profiling", "Supposed to log information to a CSV. Blame Nicalis!", &kConsoleBuiltinCommandLocalizedDescriptions[35], &kConsoleBuiltinCommandLocalizedHelpTexts[35], true, ConsoleAutocompleteType::None},
    {"profstop", "", "[BROKEN] Stop profiling", "Supposed to stop profiling but profiling is broken because we can't have nice things.", &kConsoleBuiltinCommandLocalizedDescriptions[36], &kConsoleBuiltinCommandLocalizedHelpTexts[36], true, ConsoleAutocompleteType::None},
    {"remove", "r", "Remove an item", "Removes an item from the player immediately. Accepts the same syntax as give, look at that command's help for more info.", &kConsoleBuiltinCommandLocalizedDescriptions[37], &kConsoleBuiltinCommandLocalizedHelpTexts[37], false, ConsoleAutocompleteType::Item},
    {"remove2", "r2", "Remove an item", "Removes an item from the second player immediately. Accepts the same syntax as give, look at that command's help for more info.", &kConsoleBuiltinCommandLocalizedDescriptions[38], &kConsoleBuiltinCommandLocalizedHelpTexts[38], false, ConsoleAutocompleteType::Item},
    {"removeeffect", "re", "Removes a TemporaryEffect from the character", "Removes TemporaryEffects from the main player, by ID or name. Removes Null Items by default, or prefix the ID with (c) for Collectible effects or (t) for Trinket effects.\nThis command also has shorthand which is just (re).", &kConsoleBuiltinCommandLocalizedDescriptions[39], &kConsoleBuiltinCommandLocalizedHelpTexts[39], false, ConsoleAutocompleteType::Effect},
    {"reloadfx", "", "Reload floor overlays", "Reloads the current floor's effects.", &kConsoleBuiltinCommandLocalizedDescriptions[40], &kConsoleBuiltinCommandLocalizedHelpTexts[40], false, ConsoleAutocompleteType::None},
    {"reloadshaders", "", "Reload in-game shaders", "Reloads any currently loaded shaders.", &kConsoleBuiltinCommandLocalizedDescriptions[41], &kConsoleBuiltinCommandLocalizedHelpTexts[41], false, ConsoleAutocompleteType::None},
    {"reloadwisps", "", "Reload wisps", "Reloads wisps spawned by Book of Virtues and locusts spawned by Abyss.", &kConsoleBuiltinCommandLocalizedDescriptions[42], &kConsoleBuiltinCommandLocalizedHelpTexts[42], false, ConsoleAutocompleteType::None},
    {"repeat", "", "Repeat prior commands", "Repeats the previously entered command X amount of times.\nExample:\n(giveitem 1) is used to give the player The Sad Onion. (repeat 5) is then used to give the player The Sad Onion five more times.", &kConsoleBuiltinCommandLocalizedDescriptions[43], &kConsoleBuiltinCommandLocalizedHelpTexts[43], true, ConsoleAutocompleteType::None},
    {"reseed", "", "Reseed the current floor", "Reseeds the current floor, generating a brand new layout for it.", &kConsoleBuiltinCommandLocalizedDescriptions[44], &kConsoleBuiltinCommandLocalizedHelpTexts[44], false, ConsoleAutocompleteType::None},
    {"restart", "", "Restart on a new run", "Restarts the game on a new run. Accepts an optional argument which is the character ID.\nExample:\n(restart 3) starts a new run as Judas.", &kConsoleBuiltinCommandLocalizedDescriptions[45], &kConsoleBuiltinCommandLocalizedHelpTexts[45], false, ConsoleAutocompleteType::Player},
    {"restock", "", "Restocks all shops", "Restocks all shops.", &kConsoleBuiltinCommandLocalizedDescriptions[46], &kConsoleBuiltinCommandLocalizedHelpTexts[46], false, ConsoleAutocompleteType::None},
    {"rewind", "", "Reset game to last room state", "Makes the game forget about the changes in current room and teleports Isaac back to previous room. Can be used to fix desynchronization issues if you use this command in a room where it happened. (Glowing Hourglass-like effect)", &kConsoleBuiltinCommandLocalizedDescriptions[47], &kConsoleBuiltinCommandLocalizedHelpTexts[47], false, ConsoleAutocompleteType::None},
    {"seed", "", "Start a new run with the given seed", "Starts a new run with the given seed.\nExample:\n(seed N1CA L1SY) will start a new run with the seed N1CA L1SY.", &kConsoleBuiltinCommandLocalizedDescriptions[48], &kConsoleBuiltinCommandLocalizedHelpTexts[48], false, ConsoleAutocompleteType::None},
    {"spawn", "", "Spawn an entity", "Spawns a new entity. Syntax is (type).(variant).(subtype).(champion).\nExample:\n(spawn 5.40.1) will spawn a bomb.", &kConsoleBuiltinCommandLocalizedDescriptions[49], &kConsoleBuiltinCommandLocalizedHelpTexts[49], false, ConsoleAutocompleteType::Entity},
    {"stage", "", "Go to a stage", "Immediately goes to the specified stage. Accepts (a-d) as modifiers, with (a) corresponding to WOTL alts, (b) corresponding to Afterbirth alts, (c) corresponding to Antibirth alts, and (d) corresponding to Repentance alts.\nExample:\n(stage 4d) will take the player to Ashpit II.", &kConsoleBuiltinCommandLocalizedDescriptions[50], &kConsoleBuiltinCommandLocalizedHelpTexts[50], false, ConsoleAutocompleteType::Stage},
    {"time", "", "Print game time", "Prints the total amount of time passed on the run.", &kConsoleBuiltinCommandLocalizedDescriptions[51], &kConsoleBuiltinCommandLocalizedHelpTexts[51], false, ConsoleAutocompleteType::None},
    {"testbosspool", "", "Print list of bosses for current floor", "Prints a list of boss names and percentage chance (100%=10000) for current floor.", &kConsoleBuiltinCommandLocalizedDescriptions[52], &kConsoleBuiltinCommandLocalizedHelpTexts[52], false, ConsoleAutocompleteType::None},
};

constexpr std::size_t TextLength(const char* text) noexcept {
    std::size_t length = 0;
    while (text != nullptr && text[length] != '\0') ++length;
    return length;
}

template <typename Entry, std::size_t Count>
[[nodiscard]] inline bool VisitConsoleCompletionEntries(
    const Entry (&entries)[Count], std::uint32_t language,
    AutocompleteVisitor visitor, void* user) noexcept {
    if (visitor == nullptr) return false;
    for (const Entry& entry : entries) {
        const char* text = entry.text != nullptr ? entry.text : "";
        const char* description = entry.localizedDescription != nullptr
            ? entry.localizedDescription->Select(language)
            : (entry.description != nullptr ? entry.description : "");
        if (!visitor(user, text, TextLength(text), description,
                     TextLength(description))) {
            return false;
        }
    }
    return true;
}

inline std::uint64_t& BuiltinConsoleCommandBits() noexcept {
    static std::uint64_t bits{};
    return bits;
}

inline unsigned Popcount(std::uint64_t value) noexcept {
    unsigned count = 0;
    while (value != 0) {
        value &= value - 1;
        ++count;
    }
    return count;
}

inline void EnsureBuiltinConsoleCommands() {
    const std::uint32_t language = ConsoleCatalogLanguage();
    auto& bits = BuiltinConsoleCommandBits();
    if (ConsoleCommandCount() < Popcount(bits)) bits = 0;
    for (std::size_t index = 0; index < std::size(kConsoleBuiltinCommandMetadata);
         ++index) {
        const ConsoleBuiltinCommandMetadata& command =
            kConsoleBuiltinCommandMetadata[index];
        const std::uint64_t bit = std::uint64_t{1} << index;
        const char* description = command.localizedDescription->Select(language);
        const char* helpText = command.localizedHelpText->Select(language);
        if (RegisterConsoleCommand(
                command.name, description, helpText, command.showOnMenu,
                static_cast<std::uint32_t>(command.autocompleteType)) ==
            ConsoleCommandRegistration::Added) {
            bits |= bit;
            if (command.alias != nullptr && command.alias[0] != '\0') {
                for (auto& registered : ConsoleCommands()) {
                    if (registered.name == command.name) {
                        registered.aliases.emplace_back(command.alias);
                        break;
                    }
                }
            }
            continue;
        }
        if ((bits & bit) == 0) continue;
        for (auto& registered : ConsoleCommands()) {
            if (registered.name != command.name) continue;
            if (registered.description != description) registered.description = description;
            if (registered.helpText != helpText) registered.helpText = helpText;
            break;
        }
    }
}

[[nodiscard]] inline bool VisitConsoleCompletionFixedEntries(
    ConsoleAutocompleteType type, bool greedMode, std::uint32_t language,
    AutocompleteVisitor visitor, void* user) noexcept;

[[nodiscard]] inline bool VisitConsoleCompletionFixedEntries(
    ConsoleAutocompleteType type, bool greedMode,
    AutocompleteVisitor visitor, void* user) noexcept {
    return VisitConsoleCompletionFixedEntries(
        type, greedMode, ConsoleCatalogLanguage(), visitor, user);
}

[[nodiscard]] inline bool VisitConsoleCompletionFixedEntries(
    ConsoleAutocompleteType type, bool greedMode, std::uint32_t language,
    AutocompleteVisitor visitor, void* user) noexcept {
    switch (type) {
        case ConsoleAutocompleteType::Stage:
            return greedMode
                ? VisitConsoleCompletionEntries(kConsoleCompletionGreedStageEntries, language, visitor, user)
                : VisitConsoleCompletionEntries(kConsoleCompletionStageEntries, language, visitor, user);
        case ConsoleAutocompleteType::Grid:
            return VisitConsoleCompletionEntries(kConsoleCompletionGridEntries, language, visitor, user);
        case ConsoleAutocompleteType::DebugFlag:
            return VisitConsoleCompletionEntries(kConsoleCompletionDebugFlagEntries, language, visitor, user);
        case ConsoleAutocompleteType::Combo:
            return VisitConsoleCompletionEntries(kConsoleCompletionComboEntries, language, visitor, user);
        case ConsoleAutocompleteType::Delirious:
            return VisitConsoleCompletionEntries(kConsoleCompletionDeliriousEntries, language, visitor, user);
        case ConsoleAutocompleteType::Macro:
            return VisitConsoleCompletionEntries(kConsoleCompletionMacroEntries, language, visitor, user);
        default:
            return false;
    }
}

[[nodiscard]] inline bool VisitConsoleBuiltinCommandMetadata(
    AutocompleteVisitor visitor, void* user) noexcept {
    const std::uint32_t language = ConsoleCatalogLanguage();
    if (visitor == nullptr) return false;
    for (const ConsoleBuiltinCommandMetadata& command : kConsoleBuiltinCommandMetadata) {
        const char* name = command.name != nullptr ? command.name : "";
        const char* description = command.localizedDescription->Select(language);
        if (!visitor(user, name, TextLength(name), description,
                     TextLength(description))) {
            return false;
        }
    }
    return true;
}

}  // namespace isaac::runtime::console
