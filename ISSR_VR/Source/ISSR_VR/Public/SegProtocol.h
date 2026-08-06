// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

// -----Includes----------------------------------------------------------------
#include "CoreMinimal.h"
#include "SegProtocol.generated.h"

// -----Log Categories----------------------------------------------------------
DECLARE_LOG_CATEGORY_EXTERN(LogISSR, Log, All);

// -----Constants---------------------------------------------------------------
/** Magic prefix ("NYOO") that must lead every message header, used to detect a desynced stream. */
constexpr uint32 MsgPrefix = 0x39594040; // NYOO

/** Wire message type, sent as the second field of every message header. Must match the Python side's MsgType. */
enum class EMsg : uint8
{
	None,
	MsgHello = 0x01,
	MsgReady = 0x02,
	MsgClick = 0x03,
	MsgLabels = 0x04,
	MsgFullLabels = 0x05
};

/** Point classification used by both the labelling protocol and the point store. Must match the Python side's CLASS_ID. */
UENUM(BlueprintType)
enum class EClassID : uint8
{
	Foliage = 0,
	Stem = 1,
	Ground = 2,
	Undergrowth = 3,
	Unlabelled = 31
};

// -----Structs-----------------------------------------------------------------
#pragma pack(push, 1)
/** Fixed-size header prefixed to every framed message on the wire. */
struct FHeader
{
	/** Must equal MsgPrefix or the message is treated as a desync. */
	uint32 Prefix = 0;
	/** Type of the message that follows. */
	EMsg   MsgType = EMsg::None;
	/** Size, in bytes, of the payload that follows this header. */
	uint32 PayloadSize = 0;
};
static_assert(sizeof(FHeader) == 9, "FHeader must match Python wire format");

/** Handshake payload sent by UE5 to identify the loaded point cloud. */
struct FHello
{
	/** Number of points in the point cloud. */
	uint32 PointCount = 0;
	/** Checksum of the point cloud, used to verify both sides loaded the same data. */
	uint32 Checksum = 0;
};
static_assert(sizeof(FHello) == 8, "FHello must match Python <II wire format");

/** A single point click/selection sent from UE5 to request a label update. */
struct FClick
{
	/** Index of the clicked point in the point cloud. */
	uint32	 PointIndex = 0;
	/** X coordinate of the click (currently unused, reserved). */
	float	 X = 0.f;
	/** Y coordinate of the click (currently unused, reserved). */
	float	 Y = 0.f;
	/** Z coordinate of the click (currently unused, reserved). */
	float	 Z = 0.f;
	/** Class to assign to the clicked point (and its neighbourhood). */
	EClassID ClassID = EClassID::Unlabelled;
	/** Non-zero for a positive click, zero for a negative click. */
	uint8	 PositiveFlag = 0;
};
static_assert(sizeof(FClick) == 18, "FClick must match Python <IfffBB wire format");

#pragma pack(pop)

/** A sparse set of point index -> class id assignments returned by the Python module. */
struct FLabels
{
	/** Indices of the labelled points. */
	TArray<uint32>	 PointIndices;
	/** Class assigned to each point, aligned by position with PointIndices. */
	TArray<EClassID> ClassIDs;
};

// -----Functions---------------------------------------------------------------
/**
 * Parses a message header from the front of a buffer.
 *
 * @param InData Pointer to at least sizeof(FHeader) bytes to parse.
 * @return The parsed header, or unset if the prefix does not match MsgPrefix.
 */
TOptional<FHeader>			ParseHeader(const uint8* InData);

/**
 * Encodes a HELLO message, ready to send over the socket.
 *
 * @param InHello Handshake payload to encode.
 * @return Framed HELLO message bytes.
 */
TArray<uint8>				EncodeHello(const FHello& InHello);

/**
 * Decodes a READY message payload.
 *
 * @param InPayload Raw READY payload bytes (without header).
 * @return The ready flag (0 or 1), or unset if the payload is malformed.
 */
TOptional<uint8>			DecodeReady(const TArray<uint8>& InPayload);

/**
 * Decodes a FULL_LABELS message payload.
 *
 * @param InPayload Raw FULL_LABELS payload bytes (without header).
 * @return Class id for every point in the point cloud, in point order, or unset if the payload is malformed or contains an invalid class id.
 */
TOptional<TArray<EClassID>> DecodeFullLabels(const TArray<uint8>& InPayload);

/**
 * Encodes a CLICK message, ready to send over the socket.
 *
 * @param InClick Click event to encode.
 * @return Framed CLICK message bytes, or unset if InClick has an invalid class id or positive flag.
 */
TOptional<TArray<uint8>>	EncodeClick(const FClick& InClick);

/**
 * Decodes a LABELS message payload.
 *
 * @param InPayload Raw LABELS payload bytes (without header).
 * @return The decoded point index/class id pairs, or unset if the payload is malformed or contains an invalid class id.
 */
TOptional<FLabels>			DecodeLabels(const TArray<uint8>& InPayload);
