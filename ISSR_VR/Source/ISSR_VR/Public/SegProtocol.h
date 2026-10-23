// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

// -----Includes----------------------------------------------------------------
#include "CoreMinimal.h"
#include "SegProtocol.generated.h"

// -----Log Categories----------------------------------------------------------
DECLARE_LOG_CATEGORY_EXTERN(LogISSR, Log, All);

// -----Constants---------------------------------------------------------------
constexpr uint32 MsgPrefix = 0x4F4F594E; // NYOO

/** Wire message type, the second field of every message header. Must match the Python side's MsgType. */
enum class EMsg : uint8
{
	None,
	MsgSessionConfig = 0x01, // Py  -> UE5  uint8 num_crops, uint8 max_num_clicks
	MsgCropRequest = 0x02,	 // UE5 -> Py   uint8 advance (1 next, 0 resend current)
	MsgCropCloud = 0x03,	 // Py  -> UE5  header + float32 coord[N*3] + uint8 labels[N] (+ uint8 gt[N])
	MsgClicks = 0x04,		 // UE5 -> Py   header + click[M]
	MsgLabels = 0x05,		 // Py  -> UE5  header + uint8 labels[N]
	MsgFinish = 0x06,		 // UE5 -> Py   empty
	MsgFinished = 0x07		 // Py  -> UE5  uint8 ok
};

/** Point classification. Must match the Python side's CLASS_ID. */
UENUM(BlueprintType)
enum class EClassID : uint8
{
	Foliage = 0,
	Stem = 1,
	Ground = 2,
	Unlabelled = 31
};

// -----Structs-----------------------------------------------------------------
#pragma pack(push, 1)
/** Fixed-size header prefixed to every framed message on the wire. */
struct FHeader
{
	uint32 Prefix = 0;
	EMsg   MsgType = EMsg::None;
	uint32 PayloadSize = 0;
};
static_assert(sizeof(FHeader) == 9, "FHeader must match Python <IBI wire format");

struct FSessionConfig
{
	uint8 NumCrops = 0;
	uint8 MaxNumClicks = 0;
};
static_assert(sizeof(FSessionConfig) == 2, "FSessionConfig must match Python <BB wire format");

struct FCloudHeader
{
	uint8  CropID = 0;
	uint32 NumPoints = 0;
	/** 1 if a ground-truth label array follows the predicted labels. */
	uint8 bHasGroundTruth = 0;
};
static_assert(sizeof(FCloudHeader) == 6, "FCloudHeader must match Python <BIB wire format");

struct FClicksHeader
{
	uint8  CropID = 0;
	uint32 NumClicks = 0;
};
static_assert(sizeof(FClicksHeader) == 5, "FClicksHeader must match Python <BI wire format");

struct FClick
{
	/** Position of the point in the CROP_CLOUD arrays. */
	uint32	 PointIndex = 0;
	EClassID ClassID = EClassID::Unlabelled;
};
static_assert(sizeof(FClick) == 5, "FClick must match Python <IB wire format");

struct FLabelsHeader
{
	uint8  CropID = 0;
	uint32 NumPoints = 0;
};
static_assert(sizeof(FLabelsHeader) == 5, "FLabelsHeader must match Python <BI wire format");
#pragma pack(pop)

struct FCropCloud
{
	uint8		  CropID = 0;
	TArray<float> Coord;
	TArray<uint8> Labels;
	/** Empty if the plot has no ground truth. */
	TArray<uint8> GroundTruth;
};

struct FCropLabels
{
	uint8		  CropID = 0;
	TArray<uint8> Labels;
};

// -----Functions---------------------------------------------------------------
/** @return The parsed header, or unset if the prefix does not match MsgPrefix. InData must hold sizeof(FHeader) bytes. */
TOptional<FHeader> ParseHeader(const uint8* InData);

/** @return The decoded config, or unset if the payload size is wrong. */
TOptional<FSessionConfig> DecodeSessionConfig(const TArray<uint8>& InPayload);

/** @param bInAdvance True for the next crop, false to resend the current one. */
TArray<uint8> EncodeCropRequest(bool bInAdvance);

/** @return The decoded cloud, or unset if the payload size does not match NumPoints or a label is not a known class id. */
TOptional<FCropCloud> DecodeCropCloud(const TArray<uint8>& InPayload);

/** @param InClicks One entry per clicked point of crop InCropID. */
TArray<uint8> EncodeClicks(uint8 InCropID, const TArray<FClick>& InClicks);

/** @return The decoded labels, or unset if the payload size does not match NumPoints or a label is not a known class id. */
TOptional<FCropLabels> DecodeLabels(const TArray<uint8>& InPayload);

TArray<uint8> EncodeFinish();

/** @return Whether Python wrote the LAZ, or unset if the payload size is wrong. */
TOptional<bool> DecodeFinished(const TArray<uint8>& InPayload);
