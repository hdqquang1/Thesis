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

/** Prefixes a payload with a message header to form a full wire frame. */
static TArray<uint8> Frame(const uint8* InPayload, uint32 InPayloadSize, EMsg InMsgType)
{
	TArray<uint8> OutFrame;
	OutFrame.SetNumUninitialized(sizeof(FHeader) + InPayloadSize);
	FHeader Header{ MsgPrefix, InMsgType, InPayloadSize };
	FMemory::Memcpy(OutFrame.GetData(), &Header, sizeof(FHeader));
	if (InPayloadSize > 0)
	{
		FMemory::Memcpy(OutFrame.GetData() + sizeof(FHeader), InPayload, InPayloadSize);
	}
	return OutFrame;
}

/** @return True if every label is a known EClassID; InWhat names the message in the log. */
static bool AllValidClassIDs(const TArray<uint8>& InLabels, const TCHAR* InWhat)
{
	for (int32 i = 0; i < InLabels.Num(); ++i)
	{
		switch (static_cast<EClassID>(InLabels[i]))
		{
			case EClassID::Foliage:
			case EClassID::Stem:
			case EClassID::Ground:
			case EClassID::Unlabelled:
				continue;
			default:
				UE_LOG(LogISSR, Warning, TEXT("%s: invalid class id %d at point %d"), InWhat, InLabels[i], i);
				return false;
		}
	}
	return true;
}

TOptional<FSessionConfig> DecodeSessionConfig(const TArray<uint8>& InPayload)
{
	if (InPayload.Num() != sizeof(FSessionConfig))
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeSessionConfig: invalid payload size %d (expected %d)"), InPayload.Num(), (int32)sizeof(FSessionConfig));
		return NullOpt;
	}
	FSessionConfig Out;
	FMemory::Memcpy(&Out, InPayload.GetData(), sizeof(FSessionConfig));
	return Out;
}

TArray<uint8> EncodeCropRequest(bool bInAdvance)
{
	const uint8 Advance = bInAdvance ? 1 : 0;
	return Frame(&Advance, sizeof(uint8), EMsg::MsgCropRequest);
}

TOptional<FCropCloud> DecodeCropCloud(const TArray<uint8>& InPayload)
{
	if (InPayload.Num() < (int32)sizeof(FCloudHeader))
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeCropCloud: payload too small (%d bytes)"), InPayload.Num());
		return NullOpt;
	}
	FCloudHeader Header;
	FMemory::Memcpy(&Header, InPayload.GetData(), sizeof(FCloudHeader));

	const int64 NumPoints = Header.NumPoints;
	const int64 BytesPerPoint = 12 + 1 + (Header.bHasGroundTruth ? 1 : 0); // coord + label (+ gt)
	const int64 Expected = (int64)sizeof(FCloudHeader) + NumPoints * BytesPerPoint;
	if ((int64)InPayload.Num() != Expected)
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeCropCloud: payload size mismatch (got %d bytes, expected %lld for %lld points)"),
			InPayload.Num(), Expected, NumPoints);
		return NullOpt;
	}

	FCropCloud Out;
	Out.CropID = Header.CropID;
	Out.Coord.SetNumUninitialized((int32)(NumPoints * 3));
	Out.Labels.SetNumUninitialized((int32)NumPoints);
	const uint8* P = InPayload.GetData() + sizeof(FCloudHeader);
	FMemory::Memcpy(Out.Coord.GetData(), P, NumPoints * 12);
	P += NumPoints * 12;
	FMemory::Memcpy(Out.Labels.GetData(), P, NumPoints);
	P += NumPoints;
	if (Header.bHasGroundTruth)
	{
		Out.GroundTruth.SetNumUninitialized((int32)NumPoints);
		FMemory::Memcpy(Out.GroundTruth.GetData(), P, NumPoints);
	}

	if (!AllValidClassIDs(Out.Labels, TEXT("DecodeCropCloud labels")) || !AllValidClassIDs(Out.GroundTruth, TEXT("DecodeCropCloud gt")))
	{
		return NullOpt;
	}
	return Out;
}

TArray<uint8> EncodeClicks(uint8 InCropID, const TArray<FClick>& InClicks)
{
	const FClicksHeader Header{ InCropID, (uint32)InClicks.Num() };
	TArray<uint8>	   OutPayload;
	OutPayload.SetNumUninitialized(sizeof(FClicksHeader) + InClicks.Num() * sizeof(FClick));
	FMemory::Memcpy(OutPayload.GetData(), &Header, sizeof(FClicksHeader));
	FMemory::Memcpy(OutPayload.GetData() + sizeof(FClicksHeader), InClicks.GetData(), InClicks.Num() * sizeof(FClick));
	return Frame(OutPayload.GetData(), OutPayload.Num(), EMsg::MsgClicks);
}

TOptional<FCropLabels> DecodeLabels(const TArray<uint8>& InPayload)
{
	if (InPayload.Num() < (int32)sizeof(FLabelsHeader))
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeLabels: payload too small (%d bytes)"), InPayload.Num());
		return NullOpt;
	}
	FLabelsHeader Header;
	FMemory::Memcpy(&Header, InPayload.GetData(), sizeof(FLabelsHeader));
	if ((int64)InPayload.Num() != (int64)sizeof(FLabelsHeader) + Header.NumPoints)
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeLabels: payload size mismatch (got %d bytes for %u points)"), InPayload.Num(), Header.NumPoints);
		return NullOpt;
	}

	FCropLabels Out;
	Out.CropID = Header.CropID;
	Out.Labels.SetNumUninitialized(Header.NumPoints);
	FMemory::Memcpy(Out.Labels.GetData(), InPayload.GetData() + sizeof(FLabelsHeader), Header.NumPoints);
	if (!AllValidClassIDs(Out.Labels, TEXT("DecodeLabels")))
	{
		return NullOpt;
	}
	return Out;
}

TArray<uint8> EncodeFinish()
{
	return Frame(nullptr, 0, EMsg::MsgFinish);
}

TOptional<bool> DecodeFinished(const TArray<uint8>& InPayload)
{
	if (InPayload.Num() != 1)
	{
		UE_LOG(LogISSR, Warning, TEXT("DecodeFinished: invalid payload size %d (expected 1)"), InPayload.Num());
		return NullOpt;
	}
	return InPayload[0] != 0;
}
