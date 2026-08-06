// Fill out your copyright notice in the Description page of Project Settings.

// -----Includes----------------------------------------------------------------
#include "SegProtocol.h"

// -----Log Categories----------------------------------------------------------
DEFINE_LOG_CATEGORY(LogISSR);

// -----Functions---------------------------------------------------------------
TOptional<FHeader> ParseHeader(const uint8* InData)
{
	FHeader OutHeader;
	FMemory::Memcpy(&OutHeader, InData, sizeof(FHeader));
	if (OutHeader.Prefix != MsgPrefix)
	{
		UE_LOG(LogISSR, Warning, TEXT("ParseHeader: invalid prefix 0x%08X (expected 0x%08X)"), OutHeader.Prefix, MsgPrefix);
		return NullOpt;
	}
	return OutHeader;
}

/**
 * Prefixes a payload with a message header to form a full wire frame.
 *
 * @param InPayload Pointer to the payload bytes.
 * @param InPayloadSize Size, in bytes, of the payload.
 * @param InMsgType Type of the message being framed.
 * @return The framed message (header + payload).
 */
static TArray<uint8> Frame(const uint8* InPayload, uint32 InPayloadSize, EMsg InMsgType)
{
	TArray<uint8> OutFrame;
	OutFrame.SetNumUninitialized(sizeof(FHeader) + InPayloadSize);
	FHeader Header{ MsgPrefix, InMsgType, InPayloadSize };
	FMemory::Memcpy(OutFrame.GetData(), &Header, sizeof(FHeader));
	FMemory::Memcpy(OutFrame.GetData() + sizeof(FHeader), InPayload, InPayloadSize);
	return OutFrame;
}

/**
 * Checks whether a class id is one of the known EClassID values.
 *
 * @param InClassID Class id to check.
 * @return True if InClassID is a known class.
 */
static bool IsValidClassID(EClassID InClassID)
{
	switch (InClassID)
	{
		case EClassID::Foliage:
		case EClassID::Ground:
		case EClassID::Stem:
		case EClassID::Undergrowth:
		case EClassID::Unlabelled:
			return true;
		default:
			return false;
	}
}

TArray<uint8> EncodeHello(const FHello& InHello)
{
	TArray<uint8> OutPayload;
	OutPayload.SetNumUninitialized(sizeof(FHello));
	FMemory::Memcpy(OutPayload.GetData(), &InHello, sizeof(FHello));
	return Frame(OutPayload.GetData(), OutPayload.Num(), EMsg::MsgHello);
}

TOptional<uint8> DecodeReady(const TArray<uint8>& InPayload)
{
	if (InPayload.Num() != 1)
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeReady: invalid payload size %d (expected 1)"), InPayload.Num());
		return NullOpt;
	}
	const uint8 ReadyOk = InPayload[0];
	if (ReadyOk != 0 && ReadyOk != 1)
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeReady: invalid flag value %u (expected 0 or 1)"), ReadyOk);
		return NullOpt;
	}
	return ReadyOk;
}

TOptional<TArray<EClassID>> DecodeFullLabels(const TArray<uint8>& InPayload)
{
	if (InPayload.Num() < 4)
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeFullLabels: payload too small (%d bytes, need at least 4)"), InPayload.Num());
		return NullOpt;
	}
	uint32 Count = 0;
	FMemory::Memcpy(&Count, InPayload.GetData(), sizeof(uint32));
	if (InPayload.Num() != 4 + (int64)Count) // Convert Count from uint32 to int64
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeFullLabels: payload size mismatch (got %d bytes, expected %lld for %u labels)"),
			InPayload.Num(), 4 + (int64)Count, Count);
		return NullOpt;
	}

	TArray<EClassID> OutLabels;
	OutLabels.SetNumUninitialized(Count);
	FMemory::Memcpy(OutLabels.GetData(), InPayload.GetData() + 4, Count);

	for (int32 i = 0; i < OutLabels.Num(); ++i)
	{
		if (!IsValidClassID(OutLabels[i]))
		{
			UE_LOG(LogISSR, Warning, TEXT("DecodeFullLabels: invalid class id %d at index %d"), (uint8)OutLabels[i], i);
			return NullOpt;
		}
	}

	return OutLabels;
}

TOptional<TArray<uint8>> EncodeClick(const FClick& InClick)
{
	if (!IsValidClassID(InClick.ClassID) || InClick.PositiveFlag > 1)
	{
		UE_LOG(LogISSR, Warning, TEXT("EncodeClick: invalid class id %d or positive flag %d for point %u"),
			static_cast<uint8>(InClick.ClassID), InClick.PositiveFlag, InClick.PointIndex);
		return NullOpt;
	}
	TArray<uint8> OutPayload;
	OutPayload.SetNumUninitialized(sizeof(FClick));
	FMemory::Memcpy(OutPayload.GetData(), &InClick, sizeof(FClick));
	return Frame(OutPayload.GetData(), OutPayload.Num(), EMsg::MsgClick);
}

TOptional<FLabels> DecodeLabels(const TArray<uint8>& InPayload)
{
	if (InPayload.Num() < 4)
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeLabels: payload too small (%d bytes, need at least 4)"), InPayload.Num());
		return NullOpt;
	}

	uint32 Count = 0;
	FMemory::Memcpy(&Count, InPayload.GetData(), sizeof(uint32));

	if (InPayload.Num() != 4 + 5 * (int64)Count) // Avoid overflow of 32 bits
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeLabels: payload size mismatch (got %d bytes, expected %lld for %u labels)"),
			InPayload.Num(), 4 + 5 * (int64)Count, Count);
		return NullOpt;
	}

	FLabels OutLabels;
	OutLabels.PointIndices.SetNumUninitialized(Count);
	OutLabels.ClassIDs.SetNumUninitialized(Count);
	uint32*		 PointIndicesData = OutLabels.PointIndices.GetData();
	EClassID*	 ClassIDsData = OutLabels.ClassIDs.GetData();
	const uint8* P = InPayload.GetData() + 4;

	for (uint32 i = 0; i < Count; ++i)
	{
		FMemory::Memcpy(&PointIndicesData[i], P + 5 * i, sizeof(uint32));
		FMemory::Memcpy(&ClassIDsData[i], P + 4 + 5 * i, sizeof(EClassID));
	}

	for (int32 i = 0; i < OutLabels.ClassIDs.Num(); ++i)
	{
		if (!IsValidClassID(OutLabels.ClassIDs[i]))
		{
			UE_LOG(LogISSR, Warning, TEXT("DecodeLabels: invalid class id %d at index %d (point index %u)"),
				(uint8)OutLabels.ClassIDs[i], i, OutLabels.PointIndices[i]);
			return NullOpt;
		}
	}

	return OutLabels;
}