// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "IPAddress.h"
#include "SegProtocol.h"
#include "SegPointStoreComponent.h"
#include "SegClientComponent.generated.h"

DECLARE_LOG_CATEGORY_EXTERN(LogISSRClient, Log, All);

/** State machine driving the handshake and message loop against the Python module. */
enum class ESegConnState
{
	/** Socket not yet connected, or the point store has not finished loading. */
	Disconnected,
	/** Socket connected, HELLO sent, waiting for READY. */
	Connected,
	/** READY(1) received, waiting for the initial FULL_LABELS. */
	Ready,
	/** Initial FULL_LABELS applied; steady-state CLICK/LABELS exchange. */
	Loop
};

/** Blocking-free TCP client that talks to the Python segmentation module and applies label updates to the point store. */
UCLASS(ClassGroup = (Custom), meta = (BlueprintSpawnableComponent))
class ISSR_VR_API USegClientComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	// Sets default values for this component's properties
	USegClientComponent();

	// Called every frame
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/**
	 * Closes the socket, if open.
	 *
	 * @param EndPlayReason Reason play is ending, unused.
	 */
	virtual void EndPlay(EEndPlayReason::Type EndPlayReason) override;

	/**
	 * Sends the full contents of Data over the socket, looping until every byte is sent.
	 *
	 * @param Data Bytes to send.
	 * @return True if all bytes were sent; false on a socket error or if the send would block.
	 */
	bool				 SendAll(const TArray<uint8>& Data);

	/**
	 * Encodes and sends a CLICK message for a picked point.
	 *
	 * @param PointIndex Index of the clicked point.
	 * @param Point Local-space position of the clicked point (currently unused by the wire format beyond encoding).
	 * @param ClassID Class to assign to the click.
	 * @param bPositiveFlag True for a positive click, false for a negative click.
	 * @return True if the message was encoded and sent successfully.
	 */
	bool				 SendClick(uint32 PointIndex, FVector3f Point, EClassID ClassID, bool bPositiveFlag);

	/** Drains all pending data from the socket into the internal receive Buffer without blocking. */
	void				 PollReceive();

	/** Parses and dispatches every complete framed message currently in Buffer, leaving any trailing partial message buffered. */
	void				 ProcessBuffer();

	/** @return The current connection/handshake state. */
	const ESegConnState& GetState() const { return State; };

protected:
	/** Resolves the sibling point store, creates the socket, and starts a non-blocking connect to Host:Port. */
	virtual void BeginPlay() override;

private:
	UPROPERTY(EditAnywhere, Category = "ISSR")
	FString Host = TEXT("127.0.0.1");

	UPROPERTY(EditAnywhere, Category = "ISSR")
	int32 Port = 9000;

	UPROPERTY()
	TObjectPtr<USegPointStoreComponent> PointStore = nullptr;

	ISocketSubsystem* SS = nullptr;
	FSocket*		  Socket = nullptr;
	ESegConnState	  State = ESegConnState::Disconnected;
	TArray<uint8>	  Buffer;
};
