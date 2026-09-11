#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

// A brush may extend beyond the source image. Copy only samples in the
// destination row, using texture dimensions rather than inclusive corner tags.
static inline void HorosCopyMPRBrushLine(unsigned char *destination, int width, int height,
    long row, const unsigned char *source, int sourceWidth, int sourceHeight,
    int originX, int originY, long position, bool fixedX)
{
    if (!destination || !source || width <= 0 || height <= 0 ||
        sourceWidth <= 0 || sourceHeight <= 0 || row < 0 || row >= height ||
        (size_t)width > SIZE_MAX / (size_t)height ||
        (size_t)sourceWidth > SIZE_MAX / (size_t)sourceHeight) return;
    long origin = fixedX ? originX : originY;
    int extent = fixedX ? sourceWidth : sourceHeight;
    if (position < origin) return;
    // Unsigned subtraction also handles a negative origin without signed overflow.
    unsigned long offset = (unsigned long)position - (unsigned long)origin;
    if (offset >= (unsigned long)extent) return;
    int count = fixedX ? sourceHeight : sourceWidth;
    int lineOrigin = fixedX ? originY : originX;
    for (int i = 0; i < count; i++)
    {
        int64_t column = (int64_t)lineOrigin + i;
        if (column < 0 || column >= width) continue;
        size_t sourceIndex = fixedX ? (size_t)i * sourceWidth + offset :
            (size_t)offset * sourceWidth + i;
        destination[(size_t)row * width + (size_t)column] = source[sourceIndex];
    }
}
