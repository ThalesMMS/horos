#pragma once

#include <vtkRenderWindow.h>
#include <vtkUnsignedCharArray.h>
#include <vtkNew.h>
#include <climits>
#include <cstdlib>
#include <cstring>

// The VTK window size is the drawable size in pixels, including Retina scaling.
// Return tightly packed, top-down RGB data with the caller's existing free() ownership.
inline unsigned char *HorosCopyVRFramebuffer(vtkRenderWindow *window, long *width, long *height)
{
    *width = *height = 0;
    if (!window) return nullptr;
    const int *size = window->GetSize();
    const int w = size[0], h = size[1];
    // VTK 8.2's readback array API computes its byte count as an int.
    if (w <= 0 || h <= 0 || w > INT_MAX / 3 / h) return nullptr;

    vtkNew<vtkUnsignedCharArray> pixels;
    if (window->GetPixelData(0, 0, w - 1, h - 1, 1, pixels, 0) != VTK_OK)
        return nullptr;
    const size_t rowBytes = static_cast<size_t>(w) * 3;
    unsigned char *result = static_cast<unsigned char *>(malloc(rowBytes * h));
    if (!result) return nullptr;
    for (int y = 0; y < h; ++y)
        memcpy(result + y * rowBytes, pixels->GetPointer(0) + (h - y - 1) * rowBytes, rowBytes);
    *width = w;
    *height = h;
    return result;
}

// A stereo export lays the two eyes side by side, left eye first. Each window is
// measured on its own, so a mismatch - one window resized between the two reads,
// or one not laid out yet - would slide the halves out of alignment and read past
// the end of the narrower buffer; the smaller of the two governs both instead, so
// the eyes always come out the same size. The result is tightly packed, top-down
// RGB with the caller's existing free() ownership, like the single-window read.
inline unsigned char *HorosCopyVRStereoFramebuffer(vtkRenderWindow *leftWindow,
                                                   vtkRenderWindow *rightWindow,
                                                   long *width, long *height)
{
    *width = *height = 0;
    long leftWidth = 0, leftHeight = 0, rightWidth = 0, rightHeight = 0;
    unsigned char *left = HorosCopyVRFramebuffer(leftWindow, &leftWidth, &leftHeight);
    unsigned char *right = HorosCopyVRFramebuffer(rightWindow, &rightWidth, &rightHeight);
    unsigned char *result = nullptr;
    const long eyeWidth = leftWidth < rightWidth ? leftWidth : rightWidth;
    const long eyeHeight = leftHeight < rightHeight ? leftHeight : rightHeight;
    if (left && right && eyeWidth > 0 && eyeHeight > 0 && eyeWidth <= INT_MAX / 6 / eyeHeight)
    {
        const size_t eyeRow = static_cast<size_t>(eyeWidth) * 3;
        const size_t rowBytes = eyeRow * 2;
        result = static_cast<unsigned char *>(malloc(rowBytes * eyeHeight));
        if (result)
        {
            for (long y = 0; y < eyeHeight; ++y)
            {
                memcpy(result + y * rowBytes, left + static_cast<size_t>(y) * leftWidth * 3, eyeRow);
                memcpy(result + y * rowBytes + eyeRow, right + static_cast<size_t>(y) * rightWidth * 3, eyeRow);
            }
            *width = eyeWidth * 2;
            *height = eyeHeight;
        }
    }
    free(left);
    free(right);
    return result;
}
