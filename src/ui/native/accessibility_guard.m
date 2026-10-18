// App-local ownership guard for Qt Cocoa 6.11.0–6.11.2.
// Qt's synthetic rows borrow their table ID, while realized table cells are
// owned by QAccessibleTable::childToId. Neither may delete that interface when
// the transient Cocoa representation is replaced or released.
// No accessibility attributes are hidden and no system library is modified.
// See docs/MAC_ACCESSIBILITY_FIX.md for upstream source and removal criteria.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <stdint.h>
#include <string.h>

static ptrdiff_t idOffset, rowOffset, columnOffset, roleOffset;
static void (*originalDealloc)(id, SEL);
static void (*originalRemove)(id, SEL, NSArray *);
static BOOL installed = NO;
static uint64_t preservedBorrowed = 0;
static uint64_t preservedCells = 0;

static BOOL borrowed(id element) {
    return *(id *)((char *)(void *)element + roleOffset) != nil;
}

static BOOL tableCell(id element) {
    const int row = *(int *)((char *)(void *)element + rowOffset);
    const int column = *(int *)((char *)(void *)element + columnOffset);
    return row >= 0 && column >= 0;
}

static BOOL tableOwned(id element) {
    return borrowed(element) || tableCell(element);
}

static void recordPreserved(id element) {
    if (borrowed(element))
        ++preservedBorrowed;
    else
        ++preservedCells;
}

static void guardedDealloc(id element, SEL selector) {
    // The C++ QAccessibleTable cache owns realized cells. Let its model-change
    // path delete them; a short-lived Cocoa element must not leave childToId
    // pointing to an interface that QAccessibleCache has already deleted.
    if (tableOwned(element)) {
        recordPreserved(element);
        *(uint32_t *)((char *)(void *)element + idOffset) = 0;
    }
    originalDealloc(element, selector);
}

static void guardedRemove(id cls, SEL selector, NSArray *elements) {
    NSMutableArray *owned = [NSMutableArray arrayWithCapacity:elements.count];
    for (id element in elements) {
        if (!tableOwned(element))
            [owned addObject:element];
        else
            recordPreserved(element);
    }
    originalRemove(cls, selector, owned);
}

uint64_t studio_ax_guard_preserved_borrowed(void) {
    return preservedBorrowed;
}

uint64_t studio_ax_guard_preserved_cells(void) {
    return preservedCells;
}

int studio_ax_guard_install(void) {
    if (installed) return 1;
    Class cls = objc_getClass("QMacAccessibilityElement");
    if (!cls) return -1;
    Ivar identifier = class_getInstanceVariable(cls, "axid");
    Ivar row = class_getInstanceVariable(cls, "m_rowIndex");
    Ivar column = class_getInstanceVariable(cls, "m_columnIndex");
    Ivar role = class_getInstanceVariable(cls, "synthesizedRole");
    Method dealloc = class_getInstanceMethod(cls, sel_registerName("dealloc"));
    Method remove = class_getClassMethod(cls, sel_registerName("removeElementsFromCache:"));
    // Refuse an unknown ABI rather than guessing offsets or patching other classes.
    if (!identifier || !row || !column || !role || !dealloc || !remove) return -2;
    if (strcmp(ivar_getTypeEncoding(identifier), "I") != 0
        || strcmp(ivar_getTypeEncoding(row), "i") != 0
        || strcmp(ivar_getTypeEncoding(column), "i") != 0
        || ivar_getTypeEncoding(role)[0] != '@'
        || method_getNumberOfArguments(dealloc) != 2
        || method_getNumberOfArguments(remove) != 3) return -3;
    idOffset = ivar_getOffset(identifier);
    rowOffset = ivar_getOffset(row);
    columnOffset = ivar_getOffset(column);
    roleOffset = ivar_getOffset(role);
    if (idOffset < sizeof(void *) || rowOffset < sizeof(void *) || columnOffset < sizeof(void *)
        || roleOffset < sizeof(void *)
        || rowOffset + sizeof(int) > class_getInstanceSize(cls)
        || columnOffset + sizeof(int) > class_getInstanceSize(cls)
        || roleOffset + sizeof(id) > class_getInstanceSize(cls)) return -4;
    originalDealloc = (void (*)(id, SEL))method_getImplementation(dealloc);
    originalRemove = (void (*)(id, SEL, NSArray *))method_getImplementation(remove);
    method_setImplementation(dealloc, (IMP)guardedDealloc);
    method_setImplementation(remove, (IMP)guardedRemove);
    installed = YES;
    return 1;
}
