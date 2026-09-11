#import "ViewerController.h"

@class HorosRegistrationSession, HorosRegistrationTransform, HorosLandmarkRegistrationResult, HorosGuidedCopyPlan, HorosVolumeBounds;

/// Longitudinal registration and guided ROI copy on the host's own fusion
/// route (#378, A237). The viewer that owns a fused series (the product of the
/// Fusion dialog, `blendingController`) can copy that series' ROIs onto its
/// own slices by patient position: identity when both share a Frame of
/// Reference, otherwise a rigid transform solved from named 2D point ROIs on
/// both viewers. Every step goes through `LongitudinalRegistration.swift`;
/// ROI objects, undo and notifications stay the host's. Main thread only.
///
/// Fusion plug-ins (`PluginFilter` subclasses of type `fusionFilter`, reached
/// from the same dialog through `-[PluginFilter filterImage:]` with
/// `viewerController` and its `blendingController`) can call the same
/// methods; no plug-in binary is bundled or required.
@interface ViewerController (HorosRegistration)
/// Adds "Copy ROIs from Fused Series..." to the ROI menu after the JSON export item.
+ (void)installRegistrationMenuItems;
/// Menu action: preview (quality, algorithm, placements, refusals), manual
/// offset in millimetres, confirmation, then one undoable copy.
- (IBAction)copyROIsFromFusedSeries:(id)sender;
/// Registration state of this viewer: one companion per fused series with its
/// own transform, blend (the Fusion panel's blend slider, normalised to 0...1) and verdict.
- (HorosRegistrationSession *)horosRegistrationSession;
/// Rigid transform from `moving`'s patient frame into this viewer's, from 2D
/// point ROIs paired by name (at least three), with quality.
- (HorosLandmarkRegistrationResult *)horosLandmarkRegistrationWithViewer:(ViewerController *)moving;
/// Identity for a shared Frame of Reference, else the landmark solution;
/// nil with a reason when neither is available or the fit is rejected.
- (HorosRegistrationTransform *)horosTransformFromViewer:(ViewerController *)source refusal:(NSString **)refusal;
/// Plans the copy of every ROI of `source` onto this viewer's slices.
- (HorosGuidedCopyPlan *)horosGuidedCopyPlanFromViewer:(ViewerController *)source offsetMM:(NSArray<NSNumber *> *)offsetMM refusal:(NSString **)refusal;
/// Creates the placed ROIs (new objects, provenance in comments) under one
/// undo entry; returns how many were added.
- (NSInteger)horosApplyGuidedCopyPlan:(HorosGuidedCopyPlan *)plan fromViewer:(ViewerController *)source;
/// Axis-aligned patient bounds of this viewer's volume, for the overlap check.
- (HorosVolumeBounds *)horosVolumeBounds;
/// Non-nil when the two viewers show different patients (or the same ID under
/// different names) and no explicit comparison of these two studies is stored.
- (NSString *)horosPatientComparisonPendingWithViewer:(ViewerController *)other;
/// Stores the explicit choice of these two studies as a comparison pair.
- (void)horosConfirmPatientComparisonWithViewer:(ViewerController *)other;
@end
