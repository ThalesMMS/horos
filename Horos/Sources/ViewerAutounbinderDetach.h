#import <Foundation/Foundation.h>

/// Clear NSAutounbinder's File's Owner pointer while the owner is still alive.
void HorosDetachAutounbinder(id owner);
