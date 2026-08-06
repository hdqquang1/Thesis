// Fill out your copyright notice in the Description page of Project Settings.

#include "ISSR_VR.h"
#include "Modules/ModuleManager.h"
#include "SegProtocol.h"

//class FISSR_VRModule : public FDefaultGameModuleImpl
//{
//public:
//	virtual void StartupModule() override
//	{
//		FClick C;
//		C.PointIndex = 42;
//		C.X = 1.0f;
//		C.Y = 1.0f;
//		C.Z = 1.0f;
//		C.ClassId = static_cast<uint8>(EClassId::Stem);
//		C.PositiveFlag = 1;
//
//		TArray<uint8> P;
//		EncodeClick(C, P);
//
//		FString Hex;
//		for (uint8 B : P)
//		{
//			Hex += FString::Printf(TEXT("%02X "), B);
//		}
//		UE_LOG(LogTemp, Warning, TEXT("[SegProtocol] Click bytes (%d): %s"), P.Num(), *Hex);
//
//	}
//};
//
//IMPLEMENT_PRIMARY_GAME_MODULE( FISSR_VRModule, ISSR_VR, "ISSR_VR" );
IMPLEMENT_PRIMARY_GAME_MODULE( FDefaultGameModuleImpl, ISSR_VR, "ISSR_VR" );

