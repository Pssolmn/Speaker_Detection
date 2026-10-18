// Native in-process AX stress probe. Uses only a disposable test window.
#import <AppKit/AppKit.h>
#import <objc/message.h>

static NSUInteger visit(id node, NSUInteger depth, NSMutableSet *seen) {
    if (!node || depth > 16 || seen.count > 16000) return 0;
    NSValue *key = [NSValue valueWithPointer:(void *)node];
    if ([seen containsObject:key]) return 0;
    [seen addObject:key];
    NSUInteger count = 1;
    // Children first creates Qt's synthesized table placeholders; asking for
    // selected children next is the original failing replacement/cleanup route.
    NSArray *children = nil;
    if ([node respondsToSelector:@selector(accessibilityChildren)])
        children = [[node accessibilityChildren] retain];
    if ([node respondsToSelector:@selector(accessibilitySelectedChildren)]) {
        NSArray *selected = [node accessibilitySelectedChildren];
        for (id child in selected)
            if ([child respondsToSelector:@selector(accessibilityValue)])
                (void)[child accessibilityValue];
    }
    for (id child in children) count += visit(child, depth + 1, seen);
    [children release];
    return count;
}

unsigned long studio_ax_probe(void) {
    @autoreleasepool {
        return visit(NSApp, 0, [NSMutableSet set]);
    }
}
