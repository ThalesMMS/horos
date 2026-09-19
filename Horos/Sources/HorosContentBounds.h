// Conservative display-content bounds for opening auto-zoom. No pixels are
// changed. Work is bounded to a 192 x 192 sample grid of the displayed image.
#ifndef HorosContentBounds_h
#define HorosContentBounds_h
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct { double x, y, width, height; } HorosContentRect;
typedef struct { int left, top, right, bottom, count, interiorCount; } HorosContentComponent;

static bool HorosContentIsPeripheralSupport(HorosContentComponent c, HorosContentComponent body)
{
    double w = c.right - c.left + 1, h = c.bottom - c.top + 1;
    double bodyW = body.right - body.left + 1, bodyH = body.bottom - body.top + 1;
    double cx = (c.left + c.right) * .5, cy = (c.top + c.bottom) * .5;
    // A curved table can have a large bounding box despite consisting of thin
    // rails. Require a broad component outside the main body's center region;
    // density alone would also discard some disconnected anatomy.
    bool horizontal = w >= bodyW * .9 && (cy < body.top || cy > body.bottom);
    bool vertical = h >= bodyH * .9 && (cx < body.left || cx > body.right);
    bool thinRails = c.count < w * h * .35 && c.interiorCount < c.count * .5;
    return (horizontal && ((w >= h * 2.5 && thinRails) || (w >= h * 10 && h <= bodyH * .2))) ||
           (vertical && ((h >= w * 2.5 && thinRails) || (h >= w * 10 && w <= bodyW * .2)));
}

static int HorosContentCompare(const void *a, const void *b)
{
    float x = *(const float *)a, y = *(const float *)b;
    return (x > y) - (x < y);
}

static bool HorosFindContentBounds(const float *pixels, bool rgb, bool hounsfield, size_t width,
                                   size_t height, HorosContentRect *result)
{
    if (!pixels || !result || width < 16 || height < 16 || width > SIZE_MAX / height / 4)
        return false;
    int nx = (int)(width < 192 ? width : 192), ny = (int)(height < 192 ? height : 192);
    int n = nx * ny, finiteCount = 0, borderCount = 0;
    float *values = malloc(n * sizeof(float)), *sorted = malloc(n * sizeof(float));
    float *border = malloc(n * sizeof(float));
    uint8_t *mask = calloc(n, 1);
    int *queue = malloc(n * sizeof(int));
    HorosContentComponent *components = calloc(n, sizeof(*components));
    bool found = false;
    if (!values || !sorted || !border || !mask || !queue || !components) goto done;
    for (int y = 0; y < ny; y++) for (int x = 0; x < nx; x++)
    {
        size_t offset = (size_t)((y + .5) * height / ny) * width + (size_t)((x + .5) * width / nx);
        float value = pixels[offset];
        if (rgb)
        {
            const uint8_t *p = (const uint8_t *)pixels + offset * 4;
            value = .2126f * p[1] + .7152f * p[2] + .0722f * p[3];
        }
        values[y * nx + x] = value;
        if (isfinite(value))
        {
            sorted[finiteCount++] = value;
            if (x < 2 || y < 2 || x >= nx - 2 || y >= ny - 2) border[borderCount++] = value;
        }
    }
    if (finiteCount < n * .95 || borderCount < nx + ny) goto done;
    double threshold = 0, background = 0;
    if (!hounsfield || rgb)
    {
        qsort(sorted, finiteCount, sizeof(float), HorosContentCompare);
        qsort(border, borderCount, sizeof(float), HorosContentCompare);
        double range = (double)sorted[(finiteCount - 1) * 98 / 100] - sorted[(finiteCount - 1) * 2 / 100];
        background = border[borderCount / 2];
        if (!isfinite(range) || range <= 1e-6) goto done;
        for (int i = 0; i < borderCount; i++) border[i] = fabs((double)border[i] - background);
        qsort(border, borderCount, sizeof(float), HorosContentCompare);
        // Border noise is estimated in calibrated pixel values, independently of
        // WL/WW, CLUT and MONOCHROME1 display inversion.
        threshold = fmax(range * .03, border[borderCount / 2] * 6);
    }
    // In calibrated CT, air noise and low-density table padding can connect
    // the body to the support at the generic contrast threshold. Use tissue
    // above -600 HU for connectivity; the outer soft-tissue contour and the
    // bounds' safety margin retain the chest outline around aerated lungs.
    // Other modalities/units retain the relative, polarity-independent mask.
    for (int i = 0; i < n; i++)
        mask[i] = isfinite(values[i]) && ((hounsfield && !rgb) ? values[i] > -600 : fabs(values[i] - background) > threshold);
    int componentCount = 0, largest = 0, largestIndex = 0;
    for (int i = 0; i < n; i++)
    {
        if (mask[i] != 1) continue;
        HorosContentComponent c = {i % nx, i / nx, i % nx, i / nx, 0, 0};
        int head = 0, tail = 0;
        queue[tail++] = i; mask[i] = 3; // retain the foreground bit after visiting
        while (head < tail)
        {
            int p = queue[head++], x = p % nx, y = p / nx;
            c.count++;
            if (x < c.left) c.left = x; if (x > c.right) c.right = x;
            if (y < c.top) c.top = y; if (y > c.bottom) c.bottom = y;
            bool interior = true;
            for (int dy = -1; dy <= 1; dy++) for (int dx = -1; dx <= 1; dx++)
            {
                int xx = x + dx, yy = y + dy;
                if (xx < 0 || xx >= nx || yy < 0 || yy >= ny) { interior = false; continue; }
                int next = yy * nx + xx;
                if (!(mask[next] & 1)) interior = false;
                if (mask[next] == 1) { mask[next] = 3; queue[tail++] = next; }
            }
            if (interior) c.interiorCount++;
        }
        // Reject isolated markers and thin table/overlay lines. Keep substantial
        // disconnected components (for example arms), not only the largest one.
        int w = c.right - c.left + 1, h = c.bottom - c.top + 1;
        if (w < 3 || h < 3 || c.count < w * h * .12) continue;
        if (c.count > largest) { largest = c.count; largestIndex = componentCount; }
        components[componentCount++] = c;
    }
    if (largest < n * .01) goto done;
    int left = nx, top = ny, right = -1, bottom = -1;
    for (int i = 0; i < componentCount; i++)
    {
        HorosContentComponent c = components[i];
        if (c.count < fmax(n * .002, largest * .03)) continue;
        // Keep the main component and substantial anatomy such as arms/legs.
        // Ambiguous or connected supports remain in the conservative bounds.
        if (i != largestIndex && HorosContentIsPeripheralSupport(c, components[largestIndex])) continue;
        if (c.left < left) left = c.left; if (c.right > right) right = c.right;
        if (c.top < top) top = c.top; if (c.bottom > bottom) bottom = c.bottom;
    }
    if (right < left || bottom < top) goto done;
    double x0 = (double)left * width / nx, x1 = (double)(right + 1) * width / nx;
    double y0 = (double)top * height / ny, y1 = (double)(bottom + 1) * height / ny;
    double marginX = fmax(width * .02, (x1 - x0) * .08);
    double marginY = fmax(height * .02, (y1 - y0) * .08);
    x0 = fmax(0, x0 - marginX); x1 = fmin(width, x1 + marginX);
    y0 = fmax(0, y0 - marginY); y1 = fmin(height, y1 + marginY);
    *result = (HorosContentRect){x0, y0, x1 - x0, y1 - y0};
    found = true;
done:
    free(values); free(sorted); free(border); free(mask); free(queue); free(components);
    return found;
}
#endif
