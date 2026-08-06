// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "InputMappingContext.h"
#include "InputAction.h"
#include "MotionControllerComponent.h"
#include "LidarPointCloudComponent.h"
#include "SegProtocol.h"
#include "SegClientComponent.h"
#include "SegPointStoreComponent.h"
#include "SegInteractionComponent.generated.h"

DECLARE_LOG_CATEGORY_EXTERN(LogISSRInteract, Log, All);

/** Handles VR motion-controller aiming/clicking, converting picked points into CLICK requests sent through USegClientComponent. */
UCLASS(ClassGroup = (Custom), meta = (BlueprintSpawnableComponent))
class ISSR_VR_API USegInteractionComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	// Sets default values for this component's properties
	USegInteractionComponent();
	// Called every frame
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Enhanced Input mapping context to add for the segmentation click action. */
	UPROPERTY(EditAnywhere, Category = "ISSR")
	TObjectPtr<UInputMappingContext> SegMappingContext;

	/** Enhanced Input action bound to OnClick. */
	UPROPERTY(EditAnywhere, Category = "ISSR")
	TObjectPtr<UInputAction> ClickAction;

	/** Motion controller used as the aim ray origin/direction; auto-resolved to "MotionControllerRightAim" in BeginPlay if unset. */
	UPROPERTY()
	TObjectPtr<UMotionControllerComponent> AimController;

	/** Point store queried for picking and updated on click; auto-resolved from the level in BeginPlay if unset. */
	UPROPERTY()
	TObjectPtr<USegPointStoreComponent> PointStore;

	/** Client used to send CLICK messages; auto-resolved from the level in BeginPlay if unset. */
	UPROPERTY()
	TObjectPtr<USegClientComponent> Client;

	/** Point cloud component providing the world transform for the aim ray; auto-resolved from the level in BeginPlay if unset. */
	UPROPERTY()
	TObjectPtr<ULidarPointCloudComponent> PointCloudComponent;

	/** Radius, in point-cloud local units, used when picking a point under the aim ray. */
	UPROPERTY(EditAnywhere, Category = "ISSR")
	float PickRadius = 5.0f;

	/** Class assigned to points picked while this component is active. */
	UPROPERTY(EditAnywhere, Category = "ISSR")
	EClassID ClassID = EClassID::Stem;

	/** Whether picks are treated as positive (true) or negative (false) clicks. */
	UPROPERTY(EditAnywhere, Category = "ISSR")
	bool bPositiveFlag = 1;

protected:
	/** Resolves AimController/PointStore/Client/PointCloudComponent and binds input if the pawn is already possessed. */
	virtual void BeginPlay() override;

private:
	/**
	 * Adds SegMappingContext to the player's input subsystem and binds ClickAction to OnClick.
	 *
	 * @param Pawn Owning pawn whose input component receives the binding.
	 * @param PC Controller possessing Pawn.
	 */
	void SetupInput(APawn* Pawn, APlayerController* PC);

	/** Picks the point under the current aim ray, if any, and sends it as a CLICK to Client. */
	void OnClick();

	/** Whether SetupInput has successfully bound the click action yet. */
	bool bInputBound = false;
};
