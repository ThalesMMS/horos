#ifndef HorosScrollPositionPreviewGeometry_h
#define HorosScrollPositionPreviewGeometry_h
#include <math.h>
#include <stdbool.h>

// Reorient a resliced image by quarter turns/reflections, preserving its
// physical aspect ratio. Coordinates are fractions measured from the top left.
typedef struct { bool transpose, flipX, flipY; } HorosPreviewOrientation;

static inline int HorosPreviewResliceAxis(const float source[9])
{
    // Axial -> coronal; coronal/sagittal -> axial. Choose the source pixel
    // dimension by its patient direction, not by the on-screen rotation.
    int normal = fabs(source[8]) >= fmax(fabs(source[6]), fabs(source[7])) ? 1 : 2;
    return fabs(source[normal]) > fabs(source[normal + 3]) ? 1 : 0;
}

static inline HorosPreviewOrientation HorosPreviewDisplayOrientation(const float plane[9])
{
    HorosPreviewOrientation result;
    result.transpose = fabs(plane[3]) > fabs(plane[0]);
    int across = result.transpose ? 3 : 0;
    int down = result.transpose ? 0 : 3;
    result.flipX = plane[across] < 0; // patient's left to the screen's right
    bool axial = fabs(plane[8]) >= fmax(fabs(plane[6]), fabs(plane[7]));
    result.flipY = axial ? plane[down + 1] < 0 : plane[down + 2] > 0;
    return result;
}

static inline void HorosPreviewMapPoint(HorosPreviewOrientation orientation, double x, double y,
                                       double *u, double *v)
{
    *u = orientation.transpose ? y : x;
    *v = orientation.transpose ? x : y;
    if (orientation.flipX) *u = 1 - *u;
    if (orientation.flipY) *v = 1 - *v;
}
#endif
