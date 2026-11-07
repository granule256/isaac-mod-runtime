#include "application/callback/callback_registry.hpp"

namespace isaac::runtime {

Status CallbackRegistry::Register(const CallbackDescriptor& descriptor, std::int64_t filter,
                                  CallbackPriorityValue priority) noexcept {
    if (!descriptor.valid()) {
        return Status{StatusCode::InvalidArgument};
    }
    if (count_ >= kCapacity) {
        return Status{StatusCode::CapacityExceeded};
    }
    // **追加**登记（2026-09-12 修正）。
    //
    // 这里原来对同一 `(id, owner)` 做覆盖，注释写的是"PC 上一个 Mod 只占一个回调槽" —— 那是错的：
    // PC 的 `Mod:AddCallback` 每次都新增一个回调，派发时按登记顺序**全部调用**。EID 重度依赖它
    // （同一 id 登记 5 个 `MC_POST_NEW_ROOM`、10 个 `MC_PRE_USE_ITEM`）。
    // 更糟的是 `owner` 目前是常量 `kRuntimeOwner{1,1}`（`lua_runtime.cpp`），去重键退化成"只看 id"，
    // 于是每种回调永远只剩最后一条 —— 真机报告 `01789203805` 的"注册表 7 条"正是这么来的
    // （宿主机已定量复现：同 id 登记两次，只有后者被调用，且前者既不执行也不释放引用）。
    //
    // 不同 Mod 之间的隔离仍由 `owner` 承担；同一 Mod 的多次登记按登记顺序派发
    // （`CallbackDispatcher::Dispatch` 用 `CountOf(id)` + `At(id, index)` 遍历多条，无需改动）。
    entries_[count_] = descriptor;
    // 过滤器与描述符在**同一处**写入（同一把下标），这是"两张表永不脱钩"的唯一保证点：
    // 只要新增登记路径都走这里，就不可能出现"描述符有、过滤器没跟上"的错位。
    filters_[count_] = filter;
    // 优先级与描述符同样在**同一处**写入（同一把下标）—— 三张表永不脱钩。
    priorities_[count_] = priority;
    std::size_t position = count_;
    // PC在登记时倒向找同一id中最后一个<=priority的条目。
    // NaN不满足<=；派发时重新排序或先过滤都会改变其真实顺序。
    for (std::size_t scan = count_; scan > 0; --scan) {
        const std::size_t existing = order_[scan - 1];
        if (entries_[existing].id != descriptor.id) continue;
        if (priorities_[existing] <= priority) break;
        position = scan - 1;
    }
    for (std::size_t move = count_; move > position; --move) {
        order_[move] = order_[move - 1];
    }
    order_[position] = static_cast<std::uint8_t>(count_);
    ++count_;
    return Status::Ok();
}

std::int64_t CallbackRegistry::FilterAt(std::size_t index) const noexcept {
    return index < count_ ? filters_[index] : kNoCallbackFilter;
}

CallbackPriorityValue CallbackRegistry::PriorityAt(std::size_t index) const noexcept {
    return index < count_ ? priorities_[index] : kDefaultCallbackPriority;
}

std::size_t CallbackRegistry::DispatchIndexAt(std::size_t position) const noexcept {
    return position < count_ ? order_[position] : count_;
}

const CallbackDescriptor* CallbackRegistry::Find(CallbackId id, ModHandle owner) const noexcept {
    for (std::size_t index = 0; index < count_; ++index) {
        const CallbackDescriptor& entry = entries_[index];
        if (entry.id == id && entry.owner == owner) {
            return &entry;
        }
    }
    return nullptr;
}

std::uint32_t CallbackRegistry::Remove(CallbackId id, ModHandle owner,
                                       CallbackDescriptor* removed) noexcept {
    for (std::size_t index = 0; index < count_; ++index) {
        const CallbackDescriptor& entry = entries_[index];
        if (entry.id != id || entry.owner != owner) {
            continue;
        }
        return RemoveAtIndex(index, removed);
    }
    return 0;
}

std::uint32_t CallbackRegistry::RemoveAtIndex(std::size_t index,
                                              CallbackDescriptor* removed) noexcept {
    if (index >= count_) {
        return 0;
    }
    if (removed != nullptr) {
        *removed = entries_[index];
    }
    std::size_t writeOrder = 0;
    for (std::size_t position = 0; position < count_; ++position) {
        const std::size_t registered = order_[position];
        if (registered == index) continue;
        order_[writeOrder++] = static_cast<std::uint8_t>(registered > index ? registered - 1 : registered);
    }
    for (std::size_t move = index + 1; move < count_; ++move) {
        entries_[move - 1] = entries_[move];
        // 过滤器与优先级必须跟着一起前移（见头文件里 `filters_` 的注释）：漏了这一步会让
        // 其余登记的过滤器/优先级整体错位，而症状是"别的回调静默不触发"或"顺序莫名其妙"。
        filters_[move - 1] = filters_[move];
        priorities_[move - 1] = priorities_[move];
    }
    --count_;
    // 尾槽复位：不必须（`count_` 已经把它排除在外），但留着上一次的值会让"表尾长什么样"
    // 取决于历史操作顺序，调试读数时容易看成一条真登记。
    filters_[count_] = kNoCallbackFilter;
    priorities_[count_] = kDefaultCallbackPriority;
    order_[count_] = 0;
    return 1;
}

std::uint32_t CallbackRegistry::RemoveOwner(ModHandle owner) noexcept {
    std::uint32_t removed = 0;
    for (std::size_t index = count_; index > 0; --index) {
        if (entries_[index - 1].owner == owner) {
            removed += RemoveAtIndex(index - 1);
        }
    }
    return removed;
}

std::size_t CallbackRegistry::CountOf(CallbackId id) const noexcept {
    std::size_t total = 0;
    for (std::size_t index = 0; index < count_; ++index) {
        if (entries_[index].id == id) {
            ++total;
        }
    }
    return total;
}

const CallbackDescriptor* CallbackRegistry::At(CallbackId id, std::size_t index) const noexcept {
    std::size_t seen = 0;
    for (std::size_t position = 0; position < count_; ++position) {
        if (entries_[position].id != id) {
            continue;
        }
        if (seen == index) {
            return &entries_[position];
        }
        ++seen;
    }
    return nullptr;
}

const CallbackDescriptor* CallbackRegistry::AtIndex(std::size_t index) const noexcept {
    if (index >= count_) {
        return nullptr;
    }
    return &entries_[index];
}

void CallbackRegistry::Reset() noexcept {
    entries_ = {};
    // 用哨兵值而不是全零：零是**有意义**的过滤值（`Card.CARD_FOOL` 等），
    // 全零会让"空表"与"每一条都带 0 号过滤器"长得一样。
    filters_.fill(kNoCallbackFilter);
    priorities_.fill(kDefaultCallbackPriority);
    order_ = {};
    count_ = 0;
}

} // namespace isaac::runtime
