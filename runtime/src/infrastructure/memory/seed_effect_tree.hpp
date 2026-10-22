#pragma once
#include <cstddef>
#include <cstdint>

namespace isaac::runtime::seed_effects {
// libc++ __tree<eSeedEffect>，按原生Add/RemoveSeedEffect指令布局；不使用本模块的STL分配器。
struct Node {
    Node* left{};
    Node* right{};
    Node* parent{};
    bool black{};
    std::uint8_t padding[3]{};
    std::int32_t key{};
};
struct Tree {Node* begin{};Node* root{};std::size_t size{};};
static_assert(sizeof(Node)==32 && offsetof(Node,key)==28 && offsetof(Node,black)==24);
static_assert(sizeof(Tree)==24 && offsetof(Tree,root)==8);
struct Bindings {
    Node* (*allocate)(std::size_t){};
    void (*release)(Node*){};
    void (*balance)(Node*,Node*){};
    void (*remove)(Node*,Node*){};
};
inline Node* Next(Node* n) {
    if(n->right){n=n->right;while(n->left)n=n->left;return n;}
    Node* p=n->parent;
    while(n!=p->left){n=p;p=p->parent;}
    return p;
}
template<class Accessible>
bool Write(Tree& tree,std::int32_t value,bool add,const Bindings& native,Accessible accessible) {
    if(!native.allocate||!native.release||!native.balance||!native.remove||
       !accessible(&tree,sizeof(tree)))return false;
    // 空树的end节点就是root那一格；不解引用不存在的end.parent/right。
    auto* end=reinterpret_cast<Node*>(&tree.root);
    if((tree.size==0)!=(tree.root==nullptr)||!tree.begin||
       (tree.size==0&&tree.begin!=end))return false;
    Node* parent=end;Node** slot=&tree.root;Node* found=nullptr;
    for(unsigned depth=0;*slot;++depth){
        if(depth>=64||!accessible(*slot,sizeof(Node)))return false;
        parent=*slot;
        if(parent->key==value){found=parent;break;}
        slot=value<parent->key?&parent->left:&parent->right;
    }
    if(add){
        if(found)return true;
        if(tree.begin!=end&&!accessible(tree.begin,sizeof(Node)))return false;
        auto* node=native.allocate(sizeof(Node));if(!node)return false;
        *node={};node->key=value;node->parent=parent;*slot=node;
        if(tree.begin->left)tree.begin=tree.begin->left;
        native.balance(tree.root,node);++tree.size;
    }else if(found){
        if(tree.begin==found)tree.begin=Next(found);
        --tree.size;native.remove(tree.root,found);native.release(found);
    }
    return true;
}
}
