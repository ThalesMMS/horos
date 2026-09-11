#ifndef VRRayCastZBufferGuard_h
#define VRRayCastZBufferGuard_h

#ifdef __cplusplus
extern "C" {
#endif

/* vtkFixedPointRayCastImage::GetZBufferValue indexes ZBuffer[y * width + x]
   with no NULL check and no lower bound. A zero size becomes index -1
   (ZBufferSize[0] - 1). Dental3D/CBCT still ray-casts; it must not use that
   buffer. This header is Horos-only so VTK is not rebuilt. */
static inline int HorosRayCastZBufferIsUsable(int useZBuffer, const float *zBuffer,
                                               int width, int height)
{
    return useZBuffer && zBuffer != 0 && width > 0 && height > 0;
}

#ifdef __cplusplus
}
#endif

#endif
