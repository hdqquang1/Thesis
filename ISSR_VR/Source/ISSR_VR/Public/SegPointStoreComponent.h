// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "LidarPointCloud.h"
#include "SegProtocol.h"
#include "SegPointStoreComponent.generated.h"

DECLARE_LOG_CATEGORY_EXTERN(LogISSRStore, Log, All);

/** Owns the canonical, index-stable copy of a LidarPointCloud's positions/labels and mediates all reads/writes to them. */
UCLASS(ClassGroup = (Custom), meta = (BlueprintSpawnableComponent))
class ISSR_VR_API USegPointStoreComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	// Sets default values for this component's properties
	USegPointStoreComponent();

	// Called every frame
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/**
	 * Loads PointCloudAsset and copies every point's position and ground-truth label into the canonical arrays, then computes Count and PositionsHash.
	 *
	 * @return True if at least one point was loaded; false if PointCloudAsset is unset or the cloud is empty.
	 */
	bool  BuildCanonicalArrays();

	/** Writes Count, PositionsHash, Positions, and GroundTruthLabels to "<ProjectSavedDir>/<AssetName>.bin", skipping the write if an up-to-date export already exists. */
	void  ExportCanonicalArrays();

	/** Copies every entry of Labels back onto the corresponding point's ClassificationID in PointCloudAsset. */
	void  ApplyAllLabels() const;

	/**
	 * Merges a sparse label update into Labels and applies the change to the points within the affected bounding box in PointCloudAsset.
	 *
	 * @param UpdatedLabels Point index/class id pairs to apply. Indices outside Count are skipped and logged.
	 */
	void  ApplyUpdatedLabels(const FLabels& UpdatedLabels);

	/**
	 * Finds the canonical index of the point at an exact position, via binary search over IndicesByPosition.
	 *
	 * @param Query Position to look up.
	 * @return Canonical index of the matching point, or INDEX_NONE if no point is at that exact position.
	 */
	int32 FindIndexByPosition(const FVector3f& Query) const;

	/**
	 * Raycasts into the point cloud and returns the canonical index of the closest point in front of the ray origin.
	 *
	 * @param LocalOrigin Ray origin, in the point cloud's local space.
	 * @param LocalDir Ray direction, in the point cloud's local space. Need not be normalized.
	 * @param Radius Cylinder radius, in local units, used for the line trace.
	 * @return Canonical index of the picked point, or INDEX_NONE if no point was hit or PointCloudAsset is unset.
	 */
	int32 PickIndexByRay(const FVector3f& LocalOrigin, const FVector3f& LocalDir, float Radius) const;

	/** @return True once BuildCanonicalArrays has successfully populated the canonical arrays. */
	bool					 IsLoaded() const { return bLoaded; }
	/** @return Number of points in the canonical arrays. */
	uint32					 GetCount() const { return Count; }
	/** @return Checksum of Positions, used to verify both sides of the protocol loaded the same point cloud. */
	uint32					 GetPositionsHash() const { return PositionsHash; }
	/** @return Canonical point positions, indexed the same way as GetLabels/GetGroundTruthLabels. */
	const TArray<FVector3f>& GetPositions() const { return Positions; }
	/** @return Current (mutable-elsewhere) label for every point. */
	const TArray<EClassID>&	 GetLabels() const { return Labels; }
	/** @return Mutable reference to the current label array, for bulk replacement (e.g. after a FULL_LABELS message). */
	TArray<EClassID>&		 GetLabelsMutable() { return Labels; }
	/** @return Ground-truth label loaded from the point cloud asset for every point. */
	const TArray<EClassID>&	 GetGroundTruthLabels() const { return GroundTruthLabels; }
	/** @return The assigned point cloud asset, or nullptr if unset. */
	ULidarPointCloud*		 GetPointCloudAsset() const { return PointCloudAsset; }

protected:
	/** Builds the canonical arrays, sorts the position index, and exports the canonical data to disk. */
	virtual void BeginPlay() override;

private:
	UPROPERTY(EditAnywhere, Category = "ISSR") // Allow importing point cloud through drag in Content Browser
	TObjectPtr<ULidarPointCloud> PointCloudAsset = nullptr;

	/** Canonical point positions, index-stable for the lifetime of the component. */
	TArray<FVector3f> Positions;
	/** Current, mutable label for each point, aligned with Positions. */
	TArray<EClassID>  Labels;
	/** Label loaded from the point cloud asset at BuildCanonicalArrays time, aligned with Positions. */
	TArray<EClassID>  GroundTruthLabels;
	/** Number of points in the canonical arrays. */
	uint32			  Count = 0;
	/** Checksum of Positions. */
	uint32			  PositionsHash = 0; // Checksum
	/** Whether BuildCanonicalArrays has successfully run. */
	bool			  bLoaded = false;
	/** Indices into Positions, sorted by position, for binary search in FindIndexByPosition. */
	TArray<int32>	  IndicesByPosition;
};
