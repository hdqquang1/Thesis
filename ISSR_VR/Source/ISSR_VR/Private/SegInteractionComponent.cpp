// Fill out your copyright notice in the Description page of Project Settings.

#include "SegInteractionComponent.h"
#include "EnhancedInputSubsystems.h"
#include "EnhancedInputComponent.h"
#include "DrawDebugHelpers.h"
#include "EngineUtils.h"

DEFINE_LOG_CATEGORY(LogISSRInteract);

// Sets default values for this component's properties
USegInteractionComponent::USegInteractionComponent()
{
	// Set this component to be initialized when the game starts, and to be ticked every frame.  You can turn these features
	// off to improve performance if you don't need them.
	PrimaryComponentTick.bCanEverTick = true;

	// ...
}

// Called when the game starts
void USegInteractionComponent::BeginPlay()
{
	Super::BeginPlay();

	// Blueprint defaults can't reference level actors or sibling component instances,
	// so resolve these at runtime. Hand-set values in the Details panel still win.
	// TODO: promote Store/Client to a WorldSubsystem to remove this scan.
	APawn* Pawn = Cast<APawn>(GetOwner());
	if (!Pawn)
	{
		UE_LOG(LogISSRInteract, Error, TEXT("BeginPlay: owner is not a Pawn"));
		return;
	}

	if (!AimController)
	{
		TArray<UMotionControllerComponent*> Controllers;
		Pawn->GetComponents<UMotionControllerComponent>(Controllers);
		for (UMotionControllerComponent* MC : Controllers)
		{
			if (MC->GetFName() == TEXT("MotionControllerRightAim"))
			{
				AimController = MC;
				break;
			}
		}
	}

	for (TActorIterator<AActor> It(GetWorld()); It && (!PointStore || !Client || !PointCloudComponent); ++It)
	{
		if (!PointStore)
		{
			PointStore = It->FindComponentByClass<USegPointStoreComponent>();
		}
		if (!Client)
		{
			Client = It->FindComponentByClass<USegClientComponent>();
		}
		if (!PointCloudComponent)
		{
			PointCloudComponent = It->FindComponentByClass<ULidarPointCloudComponent>();
		}
	}

	if (APlayerController* PC = Cast<APlayerController>(Pawn->GetController()))
	{
		SetupInput(Pawn, PC); // already possessed
		bInputBound = true;
	}
	else
	{
		UE_LOG(LogISSRInteract, Log, TEXT("BeginPlay: waiting for possession"));
	}
}

// Called every frame
void USegInteractionComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// ...
	// Possession can happen after BeginPlay, so keep retrying until input is bound.
	if (!bInputBound)
	{
		if (APawn* Pawn = Cast<APawn>(GetOwner()))
		{
			if (APlayerController* PC = Cast<APlayerController>(Pawn->GetController()))
			{
				SetupInput(Pawn, PC);
				bInputBound = true;
			}
		}
	}

	// Persistent aim ray so you can see where you're pointing before clicking.
	if (AimController)
	{
		const FVector Origin = AimController->GetComponentLocation();
		const FVector Dir = AimController->GetForwardVector();
		DrawDebugLine(GetWorld(), Origin, Origin + Dir * 500.0, FColor::Cyan, false, -1.0f, 0, 0.3f);
	}
}

void USegInteractionComponent::SetupInput(APawn* Pawn, APlayerController* PC)
{
	if (!SegMappingContext)
	{
		UE_LOG(LogISSRInteract, Error, TEXT("SetupInput: SegMappingContext is not set"));
	}
	else if (UEnhancedInputLocalPlayerSubsystem* Sub =
				 ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
	{
		Sub->AddMappingContext(SegMappingContext, /* Priority */ 1);
	}
	else
	{
		UE_LOG(LogISSRInteract, Error, TEXT("SetupInput: no EnhancedInputLocalPlayerSubsystem"));
	}

	if (!ClickAction)
	{
		UE_LOG(LogISSRInteract, Error, TEXT("SetupInput: ClickAction is not set"));
	}
	else if (UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(Pawn->InputComponent))
	{
		EIC->BindAction(ClickAction, ETriggerEvent::Started, this, &USegInteractionComponent::OnClick);
		UE_LOG(LogISSRInteract, Log, TEXT("SetupInput: click action bound"));
	}
	else
	{
		UE_LOG(LogISSRInteract, Error, TEXT("SetupInput: no EnhancedInputComponent on pawn"));
	}
}

void USegInteractionComponent::OnClick()
{
	if (!AimController || !PointStore || !Client || !PointCloudComponent)
	{
		UE_LOG(LogISSRInteract, Warning, TEXT("OnClick: missing reference"));
		return;
	}

	const FVector WorldOrigin = AimController->GetComponentLocation();
	const FVector WorldDir = AimController->GetForwardVector();

	const FTransform PointCloudTransform = PointCloudComponent->GetComponentTransform();
	const FVector	 LocalOrigin = PointCloudTransform.InverseTransformPosition(WorldOrigin);
	const FVector	 LocalDir = PointCloudTransform.InverseTransformVectorNoScale(WorldDir);

	// Visual feedback � 10 m ray, red, 2 s
	/*DrawDebugLine(GetWorld(), WorldOrigin, WorldOrigin + WorldDir * 1000.0,
		FColor::Red, false, 2.0f, 0, 0.5f);*/

	const int32 PointIndex = PointStore->PickIndexByRay((FVector3f)LocalOrigin, (FVector3f)LocalDir, PickRadius);
	if (PointIndex == INDEX_NONE)
	{
		UE_LOG(LogISSRInteract, Log, TEXT("OnClick: no point hit"));
		return;
	}

	const FVector3f LocalPoint = PointStore->GetPositions()[PointIndex];
	GEngine->AddOnScreenDebugMessage(-1, 3.0f, FColor::Yellow,
		FString::Printf(TEXT("Picked %d"), PointIndex));

	const FVector WorldPoint = PointCloudTransform.TransformPosition((FVector)LocalPoint);
	DrawDebugSphere(GetWorld(), WorldPoint, 10.0f, 8, FColor::Yellow, false, 2.0f);

	Client->SendClick((uint32)PointIndex, LocalPoint, ClassID, bPositiveFlag);
}