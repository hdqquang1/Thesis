// Fill out your copyright notice in the Description page of Project Settings.

#include "SegPointStoreComponent.h"
#include "Algo/Sort.h"

DEFINE_LOG_CATEGORY(LogISSRStore);

/**
 * Strict weak ordering over positions (lexicographic on X, then Y, then Z), used to sort/search IndicesByPosition.
 *
 * @param A First position.
 * @param B Second position.
 * @return True if A sorts before B.
 */
static bool PositionLess(const FVector3f& A, const FVector3f& B)
{
	if (A.X != B.X)
	{
		return A.X < B.X;
	}
	if (A.Y != B.Y)
	{
		return A.Y < B.Y;
	}
	return A.Z < B.Z;
}

// Sets default values for this component's properties
USegPointStoreComponent::USegPointStoreComponent()
{
	// Set this component to be initialized when the game starts, and to be ticked every frame.  You can turn these features
	// off to improve performance if you don't need them.
	PrimaryComponentTick.bCanEverTick = false;
}

// Called when the game starts
void USegPointStoreComponent::BeginPlay()
{
	Super::BeginPlay();

	// ...
	if (!BuildCanonicalArrays())
	{
		UE_LOG(LogISSRStore, Error, TEXT("BeginPlay: Failed to build canonical arrays - point store will not be usable"));
		return;
	}

	IndicesByPosition.SetNumUninitialized(Count);
	for (int32 i = 0; i < Positions.Num(); ++i)
	{
		IndicesByPosition[i] = i;
	}

	const double Start = FPlatformTime::Seconds();
	Algo::Sort(IndicesByPosition, [this](int32 A, int32 B) {
		return PositionLess(Positions[A], Positions[B]);
	});
	UE_LOG(LogISSRStore, Log, TEXT("BeginPlay: Built position index for %u points in %.1f ms"), Count, (FPlatformTime::Seconds() - Start) * 1000.0);

	/*if (PointCloudAsset && Positions.Num() > 1)
	{
		const FVector P0(Positions[0]);
		const FVector P1(Positions[1]);
		UE_LOG(LogISSRStore, Warning, TEXT("=== Space diagnostic ==="));
		UE_LOG(LogISSRStore, Warning, TEXT("Positions[0] = %s"), *P0.ToString());
		UE_LOG(LogISSRStore, Warning, TEXT("Positions[1] = %s"), *P1.ToString());
		UE_LOG(LogISSRStore, Warning, TEXT("Asset LocationOffset = %s"),
			*PointCloudAsset->LocationOffset.ToString());

		const FBox3f B(Positions);
		UE_LOG(LogISSRStore, Warning, TEXT("Bounds min=%s max=%s"),
			*FVector(B.Min).ToString(), *FVector(B.Max).ToString());
	}*/

	ExportCanonicalArrays();
}

// Called every frame
void USegPointStoreComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// ...
}

bool USegPointStoreComponent::BuildCanonicalArrays()
{
	if (!PointCloudAsset)
	{
		UE_LOG(LogISSRStore, Error, TEXT("BuildCanonicalArrays: PointCloudAsset is null - assign it in the Details panel"));
		return false;
	}

	UE_LOG(LogISSRStore, Log, TEXT("BuildCanonicalArrays: Loading point cloud asset %s..."), *PointCloudAsset->GetName());
	const double LoadStart = FPlatformTime::Seconds();
	PointCloudAsset->LoadAllNodes();
	// PointCloudAsset->CenterPoints(); // Remove location offset on renderer
	UE_LOG(LogISSRStore, Log, TEXT("BuildCanonicalArrays: Loaded point cloud asset %s in %.1f ms"), *PointCloudAsset->GetName(), (FPlatformTime::Seconds() - LoadStart) * 1000.0);

	const int64 NumPoints = PointCloudAsset->GetNumPoints();

	// Final count is known upfront (bVisibleOnly = false visits every point exactly once),
	// so size the arrays once and write by index instead of growing them one Add() at a time.
	Positions.SetNumUninitialized((int32)NumPoints);
	Labels.SetNumUninitialized((int32)NumPoints);
	GroundTruthLabels.SetNumUninitialized((int32)NumPoints);

	const double IterStart = FPlatformTime::Seconds();
	int32		 i = 0;
	PointCloudAsset->ExecuteActionOnAllPoints(
		[this, &i](FLidarPointCloudPoint* Point) {
			Positions[i] = Point->Location;
			Labels[i] = EClassID::Unlabelled;
			GroundTruthLabels[i] = static_cast<EClassID>(Point->ClassificationID);
			++i;
		},
		/* bVisibleOnly = */ false);

	Count = (uint32)Positions.Num();
	PositionsHash = FCrc::MemCrc32(Positions.GetData(), Count * sizeof(FVector3f));
	bLoaded = true;

	if (Count == 0)
	{
		UE_LOG(LogISSRStore, Warning, TEXT("BuildCanonicalArrays: %s loaded with 0 points"), *PointCloudAsset->GetName());
	}
	else
	{
		UE_LOG(LogISSRStore, Log, TEXT("BuildCanonicalArrays: Built canonical arrays: %u points, hash 0x%08X in %.1f ms"), Count, PositionsHash, (FPlatformTime::Seconds() - IterStart) * 1000.0);
	}
	return Count > 0;
}

void USegPointStoreComponent::ExportCanonicalArrays()
{
	const FString Path = FPaths::ProjectSavedDir() / PointCloudAsset->GetName() + TEXT(".bin");

	if (FPaths::FileExists(Path))
	{
		TUniquePtr<FArchive> Reader(IFileManager::Get().CreateFileReader(*Path));
		if (!Reader)
		{
			UE_LOG(LogISSRStore, Error, TEXT("ExportCanonicalArrays: Failed to open %s for reading, will attempt to overwrite"), *Path);
			return;
		}
		uint32 ExistingCount = 0;
		uint32 ExistingHash = 0;
		if (Reader->TotalSize() >= 8)
		{
			Reader->Serialize(&ExistingCount, sizeof(uint32));
			Reader->Serialize(&ExistingHash, sizeof(uint32));
		}
		else
		{
			UE_LOG(LogISSRStore, Warning, TEXT("ExportCanonicalArrays: %s is truncated (%lld bytes, expected at least 8) - rewriting"), *Path, Reader->TotalSize());
		}
		Reader->Close();

		if (ExistingCount == Count && ExistingHash == PositionsHash)
		{
			UE_LOG(LogISSRStore, Log, TEXT("ExportCanonicalArrays: Export up to date at %s (%u points, hash 0x%08X)"), *Path, Count, PositionsHash);
			return;
		}
		UE_LOG(LogISSRStore, Log, TEXT("ExportCanonicalArrays: Export stale at %s (had %u points/0x%08X, now %u points/0x%08X), rewriting"),
			*Path, ExistingCount, ExistingHash, Count, PositionsHash);
	}

	const double Start = FPlatformTime::Seconds();

	TUniquePtr<FArchive> Writer(IFileManager::Get().CreateFileWriter(*Path));
	if (!Writer)
	{
		UE_LOG(LogISSRStore, Error, TEXT("ExportCanonicalArrays: Failed to open %s for writing"), *Path);
		return;
	}

	Writer->Serialize(&Count, sizeof(uint32));
	Writer->Serialize(&PositionsHash, sizeof(uint32));
	Writer->Serialize(Positions.GetData(), (int64)Count * sizeof(FVector3f));
	Writer->Serialize(GroundTruthLabels.GetData(), (int64)Count * sizeof(uint8));

	if (Writer->IsError())
	{
		UE_LOG(LogISSRStore, Error, TEXT("ExportCanonicalArrays: Failed to write %u points to %s"), Count, *Path);
		return;
	}

	if (!Writer->Close())
	{
		UE_LOG(LogISSRStore, Error, TEXT("ExportCanonicalArrays: Failed to close writer for %s"), *Path);
		return;
	}

	UE_LOG(LogISSRStore, Log, TEXT("ExportCanonicalArrays: Exported %u points to %s in %.1f ms"), Count, *Path, (FPlatformTime::Seconds() - Start) * 1000.0);
	return;
}

void USegPointStoreComponent::ApplyAllLabels() const
{
	if (!PointCloudAsset)
	{
		UE_LOG(LogISSRStore, Warning, TEXT("ApplyAllLabels: no PointCloudAsset assigned"));
		return;
	}
	if ((uint32)Labels.Num() != Count)
	{
		UE_LOG(LogISSRStore, Warning, TEXT("ApplyAllLabels: label count %d does not match point count %u - skipping"), Labels.Num(), Count);
		return;
	}

	const double Start = FPlatformTime::Seconds();
	int32		 i = 0;
	PointCloudAsset->ExecuteActionOnAllPoints(
		[this, &i](FLidarPointCloudPoint* P) {
			if (i < (int32)Count)
			{
				P->ClassificationID = static_cast<uint8>(Labels[i]);
			}
			++i;
		},
		/* bVisibleOnly = */ false);

	UE_LOG(LogISSRStore, Log, TEXT("ApplyAllLabels: Applied %d labels to point cloud in %.1f ms"),
		i, (FPlatformTime::Seconds() - Start) * 1000.0);
}

void USegPointStoreComponent::ApplyUpdatedLabels(const FLabels& UpdatedLabels)
{
	if (!PointCloudAsset)
	{
		UE_LOG(LogISSRStore, Warning, TEXT("ApplyUpdatedLabels: no PointCloudAsset assigned"));
		return;
	}

	const double Start = FPlatformTime::Seconds();
	int32		 OutOfRangeCount = 0;

	for (int32 i = 0; i < UpdatedLabels.PointIndices.Num(); ++i)
	{
		const uint32 Idx = UpdatedLabels.PointIndices[i];
		if (Idx < Count)
		{
			Labels[Idx] = UpdatedLabels.ClassIDs[i];
		}
		else
		{
			++OutOfRangeCount;
		}
	}
	if (OutOfRangeCount > 0)
	{
		UE_LOG(LogISSRStore, Warning, TEXT("ApplyUpdatedLabels: %d/%d point indices were out of range (Count=%u)"),
			OutOfRangeCount, UpdatedLabels.PointIndices.Num(), Count);
	}

	// Bounding box over the changed positions
	FBox3f Box(EForceInit::ForceInit);
	for (uint32 Idx : UpdatedLabels.PointIndices)
	{
		if (Idx < Count)
		{
			Box += Positions[Idx];
		}
	}
	Box = Box.ExpandBy(1.0f); // guard against float edge cases

	// One spatial query; write each visited point's current label
	int32 VisitedCount = 0;
	PointCloudAsset->ExecuteActionOnPointsInBox(
		[this, &VisitedCount](FLidarPointCloudPoint* P) {
			const int32 Idx = FindIndexByPosition(P->Location);
			if (Idx != INDEX_NONE)
			{
				P->ClassificationID = (uint8)Labels[Idx];
				++VisitedCount;
			}
		},
		(FBox)Box, /* bVisibleOnly = */ false);

	UE_LOG(LogISSRStore, Log, TEXT("ApplyUpdatedLabels: Applied updated labels to %d points within bounding box in %.1f ms"),
		VisitedCount, (FPlatformTime::Seconds() - Start) * 1000.0);
}

int32 USegPointStoreComponent::FindIndexByPosition(const FVector3f& Query) const
{
	const int32 Idx = Algo::LowerBound(
		IndicesByPosition, Query,
		[this](int32 I, const FVector3f& V) {
			return PositionLess(Positions[I], V);
		});

	if (Idx >= (int32)Count)
	{
		return INDEX_NONE;
	}

	const int32 Candidate = IndicesByPosition[Idx];
	if (Positions[Candidate] != Query)
	{
		UE_LOG(LogISSRStore, Verbose, TEXT("FindIndexByPosition: no exact match for (%.2f, %.2f, %.2f)"), Query.X, Query.Y, Query.Z);
		return INDEX_NONE;
	}
	return Candidate;
}

int32 USegPointStoreComponent::PickIndexByRay(const FVector3f& LocalOrigin, const FVector3f& LocalDir, float Radius) const
{
	if (!PointCloudAsset)
	{
		UE_LOG(LogISSRStore, Warning, TEXT("PickIndexByRay: no PointCloudAsset assigned"));
		return INDEX_NONE;
	}

	const double				   Start = FPlatformTime::Seconds();
	FVector3f					   Dir = LocalDir.GetSafeNormal();
	const FLidarPointCloudRay	   Ray(LocalOrigin, Dir);
	TArray<FLidarPointCloudPoint*> Hits;
	if (!PointCloudAsset->LineTraceMulti(Ray, Radius, /* bVisibleOnly = */ false, Hits))
	{
		UE_LOG(LogISSRStore, Verbose, TEXT("PickIndexByRay: no hits from (%.1f, %.1f, %.1f) along (%.2f, %.2f, %.2f), radius %.2f"),
			LocalOrigin.X, LocalOrigin.Y, LocalOrigin.Z, Dir.X, Dir.Y, Dir.Z, Radius);
		return INDEX_NONE;
	}

	UE_LOG(LogISSRStore, Verbose, TEXT("PickIndexByRay: Raycast hits %d points"), Hits.Num());

	// Pick the hit with the smallest positive projected distance along the ray
	const FLidarPointCloudPoint* Best = nullptr;
	float						 MinProjection = TNumericLimits<float>::Max();

	for (const FLidarPointCloudPoint* Hit : Hits)
	{
		const float Projection = FVector3f::DotProduct(Hit->Location - LocalOrigin, Dir);
		if (Projection < 0.0f)
		{
			continue;
		}
		if (Projection < MinProjection)
		{
			MinProjection = Projection;
			Best = Hit;
		}
	}

	if (!Best)
	{
		UE_LOG(LogISSRStore, Verbose, TEXT("PickIndexByRay: %d hits but none in front of the ray origin"), Hits.Num());
		return INDEX_NONE;
	}

	UE_LOG(LogISSRStore, Verbose, TEXT("PickIndexByRay: Best hit at %.2f units along ray, location (%.1f, %.1f, %.1f), took %.2f ms"),
		MinProjection, Best->Location.X, Best->Location.Y, Best->Location.Z, (FPlatformTime::Seconds() - Start) * 1000.0);
	return FindIndexByPosition(Best->Location);
}