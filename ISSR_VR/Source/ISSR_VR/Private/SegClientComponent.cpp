// Fill out your copyright notice in the Description page of Project Settings.

#include "SegClientComponent.h"

DEFINE_LOG_CATEGORY(LogISSRClient);

/**
 * Converts a connection state to a display string for logging.
 *
 * @param InState State to convert.
 * @return Human-readable name of InState.
 */
static const TCHAR* ToString(ESegConnState InState)
{
	switch (InState)
	{
		case ESegConnState::Disconnected:
			return TEXT("Disconnected");
		case ESegConnState::Connected:
			return TEXT("Connected");
		case ESegConnState::Ready:
			return TEXT("Ready");
		case ESegConnState::Loop:
			return TEXT("Loop");
		default:
			return TEXT("Unknown");
	}
}

/**
 * Assigns a new connection state and logs the transition.
 *
 * @param State State variable to update, by reference.
 * @param NewState New state to set.
 */
static void SetState(ESegConnState& State, ESegConnState NewState)
{
	UE_LOG(LogISSRClient, Log, TEXT("SetState: %s -> %s"), ToString(State), ToString(NewState));
	State = NewState;
}

// Sets default values for this component's properties
USegClientComponent::USegClientComponent()
{
	// Set this component to be initialized when the game starts, and to be ticked every frame.  You can turn these features
	// off to improve performance if you don't need them.
	PrimaryComponentTick.bCanEverTick = true;

	// ...
}

// Called when the game starts
void USegClientComponent::BeginPlay()
{
	Super::BeginPlay();

	// ...
	PointStore = GetOwner()->FindComponentByClass<USegPointStoreComponent>();
	if (!PointStore)
	{
		UE_LOG(LogISSRClient, Error, TEXT("BeginPlay: No USegPointStoreComponent found on owner %s"), *GetOwner()->GetName());
	}

	SS = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	Socket = SS->CreateSocket(NAME_Stream, TEXT("SegClient"), false);
	if (!Socket)
	{
		UE_LOG(LogISSRClient, Error, TEXT("BeginPlay: Failed to create socket for %s:%d"), *Host, Port);
		return;
	}
	Socket->SetNonBlocking(true); // TODO: Write a thread for connection instead

	TSharedRef<FInternetAddr> Addr = SS->CreateInternetAddr();
	bool					  bValid = false;
	Addr->SetIp(*Host, bValid);
	Addr->SetPort(Port);

	if (!bValid)
	{
		UE_LOG(LogISSRClient, Error, TEXT("BeginPlay: Invalid IP address \"%s\""), *Host);
		SS->DestroySocket(Socket);
		Socket = nullptr;
		return;
	}

	UE_LOG(LogISSRClient, Log, TEXT("BeginPlay: Connecting to %s:%d..."), *Host, Port);
	if (!Socket->Connect(*Addr))
	{
		// Non-blocking connect: EWOULDBLOCK/EINPROGRESS is expected here, not necessarily an error.
		ESocketErrors Err = SS->GetLastErrorCode();
		UE_LOG(LogISSRClient, Warning, TEXT("BeginPlay: Connect returned false (this is expected for a non-blocking socket), error: %s"), SS->GetSocketError(Err));
	}
}

// Called every frame
void USegClientComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// ...
	if (!Socket)
	{
		return;
	}

	if (State == ESegConnState::Disconnected)
	{
		if (!PointStore || !PointStore->IsLoaded())
		{
			return;
		}
		if (Socket->GetConnectionState() == SCS_Connected)
		{
			SetState(State, ESegConnState::Connected);
			FHello Hello{ PointStore->GetCount(), PointStore->GetPositionsHash() };
			SendAll(EncodeHello(Hello));
			UE_LOG(LogISSRClient, Log, TEXT("TickComponent: Sent HELLO (points=%u, hash=0x%08X)"), Hello.PointCount, Hello.Checksum);
		}
		return; // nothing else to do until connected
	}

	PollReceive();
	ProcessBuffer();
}

void USegClientComponent::EndPlay(EEndPlayReason::Type EndPlayReason)
{
	Super::EndPlay(EndPlayReason);
	if (Socket)
	{
		UE_LOG(LogISSRClient, Log, TEXT("EndPlay: Closing socket (state was %s)"), ToString(State));
		Socket->Close();
		SS->DestroySocket(Socket);
		Socket = nullptr;
	}
}

bool USegClientComponent::SendAll(const TArray<uint8>& Data)
{
	const double Start = FPlatformTime::Seconds();
	int32		 TotalSent = 0;
	while (TotalSent < Data.Num())
	{
		int32 Sent = 0;
		if (!Socket->Send(Data.GetData() + TotalSent, Data.Num() - TotalSent, Sent))
		{
			ESocketErrors Err = SS->GetLastErrorCode();
			UE_LOG(LogISSRClient, Error, TEXT("SendAll: Send() failed after %d/%d bytes, error: %s"), TotalSent, Data.Num(), SS->GetSocketError(Err));
			return false;
		}
		if (Sent == 0) // Kernel's send buffer is full
		{
			UE_LOG(LogISSRClient, Error, TEXT("SendAll: Send would block with %d/%d bytes remaining - not handled yet"), Data.Num() - TotalSent, Data.Num());
			return false;
		}
		TotalSent += Sent;
	}
	UE_LOG(LogISSRClient, Verbose, TEXT("SendAll: Sent %d bytes in %.2f ms"), TotalSent, (FPlatformTime::Seconds() - Start) * 1000.0);
	return true;
}

bool USegClientComponent::SendClick(uint32 PointIndex, FVector3f Point, EClassID ClassID, bool bPositiveFlag)
{
	if (State != ESegConnState::Loop)
	{
		UE_LOG(LogISSRClient, Error, TEXT("SendClick: Invalid state to send click"));
		return false;
	}

	const TOptional<TArray<uint8>> Msg = EncodeClick({ PointIndex, Point.X, Point.Y, Point.Z, ClassID, (uint8)bPositiveFlag });
	if (!Msg.IsSet())
	{
		return false;
	}
	if (!SendAll(Msg.GetValue()))
	{
		return false;
	}
	return true;
}

void USegClientComponent::PollReceive()
{
	uint32 PendingSize = 0;
	while (Socket->HasPendingData(PendingSize))
	{
		TArray<uint8> Chunk;
		Chunk.SetNumUninitialized(PendingSize);
		int32 BytesRead = 0;
		if (!Socket->Recv(Chunk.GetData(), Chunk.Num(), BytesRead))
		{
			ESocketErrors Err = SS->GetLastErrorCode();
			UE_LOG(LogISSRClient, Warning, TEXT("PollReceive: Recv() failed, error: %s"), SS->GetSocketError(Err));
			break;
		}
		Chunk.SetNum(BytesRead); // Recv may give fewer than promised
		UE_LOG(LogISSRClient, Verbose, TEXT("PollReceive: Received %d bytes (buffer now %d bytes)"), BytesRead, Buffer.Num() + BytesRead);
		Buffer.Append(Chunk);
	}
}

void USegClientComponent::ProcessBuffer()
{
	while (true)
	{
		if ((int64)Buffer.Num() < (int64)sizeof(FHeader))
		{
			break;
		}

		TOptional<FHeader> ParsedHeader = ParseHeader(Buffer.GetData());
		if (!ParsedHeader)
		{
			UE_LOG(LogISSRClient, Error, TEXT("ProcessBuffer: Connection desynced, dropping %d buffered bytes"), Buffer.Num());
			Buffer.Reset();
			break;
		}
		const FHeader& Header = *ParsedHeader;

		if (Buffer.Num() < (int64)sizeof(FHeader) + (int64)Header.PayloadSize)
		{
			UE_LOG(LogISSRClient, Verbose, TEXT("ProcessBuffer: Waiting for more data: have %d bytes, need %d for msg 0x%02X"),
				Buffer.Num(), (int32)sizeof(FHeader) + (int32)Header.PayloadSize, (uint8)Header.MsgType);
			break;
		}

		TArray<uint8> Payload;
		Payload.SetNumUninitialized(Header.PayloadSize);
		FMemory::Memcpy(Payload.GetData(), Buffer.GetData() + sizeof(FHeader), Header.PayloadSize);

		switch (Header.MsgType)
		{
			case EMsg::MsgReady:
			{
				if (State != ESegConnState::Connected)
				{
					UE_LOG(LogISSRClient, Warning, TEXT("ProcessBuffer: Received Ready message in state %s, expected Connected - ignoring"), ToString(State));
					break;
				}
				TOptional<uint8> ReadyOk = DecodeReady(Payload);
				if (!ReadyOk)
				{
					UE_LOG(LogISSRClient, Warning, TEXT("ProcessBuffer: Failed to decode Ready message (%d byte payload)"), Payload.Num());
					break; // Failed decode on well-frame message is recoverable
				}
				if (!*ReadyOk)
				{
					UE_LOG(LogISSRClient, Warning, TEXT("ProcessBuffer: Python module reported not ready; aborting handshake"));
					break;
				}
				SetState(State, ESegConnState::Ready);
				UE_LOG(LogISSRClient, Log, TEXT("ProcessBuffer: Python module ready"));
				break;
			}
			case EMsg::MsgFullLabels:
			{
				if (State != ESegConnState::Ready)
				{
					UE_LOG(LogISSRClient, Warning, TEXT("ProcessBuffer: Received FullLabels message in state %s, expected Ready - ignoring"), ToString(State));
					break;
				}
				const double Start = FPlatformTime::Seconds();
				TOptional<TArray<EClassID>> DecodedLabels = DecodeFullLabels(Payload);
				if (!DecodedLabels)
				{
					UE_LOG(LogISSRClient, Warning, TEXT("ProcessBuffer: Failed to decode FullLabels message (%d byte payload)"), Payload.Num());
					break;
				}
				UE_LOG(LogISSRClient, Log, TEXT("ProcessBuffer: Received full labels (%d labels) in %.2f ms"), DecodedLabels->Num(), (FPlatformTime::Seconds() - Start) * 1000.0);
				PointStore->GetLabelsMutable() = MoveTemp(*DecodedLabels);
				PointStore->ApplyAllLabels();
				UE_LOG(LogISSRClient, Log, TEXT("ProcessBuffer: Applied full labels to point cloud (%u labels) in %.2f ms"), PointStore->GetCount(), (FPlatformTime::Seconds() - Start) * 1000.0);
				SetState(State, ESegConnState::Loop);
			}
			case EMsg::MsgLabels:
			{
				if (State != ESegConnState::Loop)
				{
					UE_LOG(LogISSRClient, Warning, TEXT("ProcessBuffer: Received Labels message in state %s, expected Loop - ignoring"), ToString(State));
					break;
				}
				const double Start = FPlatformTime::Seconds();
				TOptional<FLabels> UpdatedLabels = DecodeLabels(Payload);
				if (!UpdatedLabels)
				{
					UE_LOG(LogISSRClient, Warning, TEXT("ProcessBuffer: Failed to decode Labels message (%d byte payload)"), Payload.Num());
					break;
				}
				UE_LOG(LogISSRClient, Log, TEXT("ProcessBuffer: Received updated labels (%d labels) in %.2f ms"), UpdatedLabels->PointIndices.Num(), (FPlatformTime::Seconds() - Start) * 1000.0);
				PointStore->ApplyUpdatedLabels(*UpdatedLabels);
				UE_LOG(LogISSRClient, Log, TEXT("ProcessBuffer: Applied updated labels (%d labels) in %.2f ms"), UpdatedLabels->PointIndices.Num(), (FPlatformTime::Seconds() - Start) * 1000.0);
				break;
			}
			default:
				UE_LOG(LogISSRClient, Warning, TEXT("ProcessBuffer: Unknown message type 0x%02X (%d byte payload) - discarding"), (uint8)Header.MsgType, Header.PayloadSize);
				break;
		}

		Buffer.RemoveAt(0, (int64)sizeof(FHeader) + (int64)Header.PayloadSize);
	}
}