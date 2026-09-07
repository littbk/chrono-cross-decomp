#include "common.h"
#include "system/sound.h"
#include "system/soundCutscene.h"
#include "system/soundCommand.h"



// the instrument index window that is eligible for bank remap
#define SOUND_BANK_REMAP_BASE_INDEX          0x20u       // first remappable instrument
#define SOUND_BANK_REMAP_COUNT               0x40u       // 64 instruments (0x20..0x5F)

// how far to shift SPU sample addresses when remapping
#define SOUND_BANK_SPU_ADDR_OFFSET           0x30000u

extern s32 D_80094FAC[];
extern s32 D_80094FFC;

//----------------------------------------------------------------------------------------------------------------------
u16 Sound_MapInstrumentToAltSampleBank( u32 in_StatusFlags, FSoundChannel* in_pChannel )
{
    if( in_StatusFlags & SOUND_BANK_FLAG_ALT_SAMPLE_BANK &&
            (in_pChannel->InstrumentIndex - SOUND_BANK_REMAP_BASE_INDEX) < SOUND_BANK_REMAP_COUNT
    )
    {
        in_pChannel->VoiceParams.StartAddress += SOUND_BANK_SPU_ADDR_OFFSET;
        in_pChannel->VoiceParams.LoopAddress  += SOUND_BANK_SPU_ADDR_OFFSET;
        in_pChannel->InstrumentIndex          += SOUND_BANK_REMAP_BASE_INDEX; // mirror into alt-bank instrument table
    }
    return in_pChannel->InstrumentIndex;
}

//----------------------------------------------------------------------------------------------------------------------
u16 Sound_MapInstrumentToBaseSampleBank( u32 in_StatusFlags, FSoundChannel* in_Channel )
{
    if( (in_StatusFlags & SOUND_BANK_FLAG_ALT_SAMPLE_BANK) && 
            (in_Channel->InstrumentIndex - SOUND_BANK_REMAP_BASE_INDEX) < SOUND_BANK_REMAP_COUNT
    )
    {
        in_Channel->VoiceParams.StartAddress -= SOUND_BANK_SPU_ADDR_OFFSET;
        in_Channel->VoiceParams.LoopAddress  -= SOUND_BANK_SPU_ADDR_OFFSET;
        in_Channel->InstrumentIndex          -= SOUND_BANK_REMAP_BASE_INDEX;
    }
    return in_Channel->InstrumentIndex;
}

//----------------------------------------------------------------------------------------------------------------------
#ifndef NON_MATCHING
INCLUDE_ASM("asm/slps_023.64/nonmatchings/system/sound2", Sound_ReconcileSavedMusicVoices);
#else
void Sound_ReconcileSavedMusicVoices( void )
{
    u32 channelBit;
    u32* voiceNumber;
    u32 savedKeyed;
    s32 count;
    s32 voiceIndex;
    u32 keyOffFlags;
    u32 voicesToKeyOff;
    u32 activeAllocated;
    u32 savedAllocated;
    u32 activeKeyed;
    u32 bit;
    u32 combined;
    u32 allVoices;
    if( g_pSuspendedMusicContext != 0 )
    {
        allVoices = 0xFFFFFF;
        keyOffFlags = 0;
        savedKeyed = g_pSuspendedMusicContext->KeyedMask;
        activeKeyed = g_pActiveMusicContext->KeyedMask;
        activeAllocated = g_pActiveMusicContext->AllocatedVoiceMask;
        savedAllocated = g_pSuspendedMusicContext->AllocatedVoiceMask;
        activeKeyed &= activeAllocated;
        savedKeyed &= savedAllocated;
        combined = ( ~activeKeyed ) | savedKeyed;
        voicesToKeyOff = ( ( ~( savedAllocated & combined ) ) & activeAllocated ) & allVoices;
        voiceIndex = 0;
        while( voicesToKeyOff != 0 )
        {
            bit = 1 << voiceIndex;
            if( voicesToKeyOff & bit )
            {
                count = 0x20;
                channelBit = bit;
                voiceNumber = &g_pSecondaryMusicChannels->VoiceParams.AssignedVoiceNumber;
                do
                {
                    if( ( *voiceNumber ) == voiceIndex )
                    {
                        *voiceNumber = 0x18;
                        keyOffFlags |= channelBit;
                    }
                    count--;
                    voiceNumber = (u32*)( ( (u8*)voiceNumber ) + ( sizeof( FSoundChannel ) ) );
                } while( count != 0 );
                voicesToKeyOff &= ~( 1 << voiceIndex );
            }
            voiceIndex++;
        }

        g_Sound_SfxState.KeyOffFlags = keyOffFlags | g_Sound_SfxState.KeyOffFlags;
    }
}
#endif

//----------------------------------------------------------------------------------------------------------------------
// Completely unused in the codebase - modifies a struct, but I'm unaware of what struct exactly (this is a pure guess...)
s32 func_8004DED8( FSoundMusicContext* in_pStruct )
{
    s32 count;
    u32 bit;

    count = 0;
    bit = 1;

    if( in_pStruct->ActiveChannelMask != 0 )
    {
        do
        {
            if( in_pStruct->ActiveChannelMask & bit )
            {
                count++;
            }
            bit <<= 1;
            if( bit == 0 )
            {
                break;
            }
        } while( in_pStruct->ActiveChannelMask >= bit );
    }

    return count;
}

//----------------------------------------------------------------------------------------------------------------------
void Sound_ResetChannel( FSoundChannel* in_pChannel, u8* in_ProgramCounter )
{
    in_pChannel->VolumeBalance = 0x6E00;
    in_pChannel->Volume = 0x32000000;
    in_pChannel->ProgramCounter = in_ProgramCounter;
    in_pChannel->Transpose = 0;
    in_pChannel->FineTune = 0;
    in_pChannel->PortamentoSteps = 0;
    in_pChannel->PitchSlide = 0;
    in_pChannel->PitchBendSlideTranspose = 0;
    in_pChannel->PitchSlideStepsCurrent = 0;
    in_pChannel->FixedNoteLength = 0;
    in_pChannel->LengthStored = 0;
    in_pChannel->ChannelVolumeSlideLength = 0;
    in_pChannel->FinePitchDelta = 0;
    in_pChannel->RandomPitchDepth = 0;
    in_pChannel->LoopStackTop = 0;
    in_pChannel->UpdateFlags = 0;
    in_pChannel->AutoPanVolume = 0;
    in_pChannel->Articulation = 0;
    in_pChannel->OpcodeStepCounter = -1;
    in_pChannel->VoiceParams.VolumeScale = 0;
    in_pChannel->AutoPanDepth = 0;
    in_pChannel->TremeloDepth = 0;
    in_pChannel->VibratoDepth = 0;
    in_pChannel->AutoPanDepthSlideLength = 0;
    in_pChannel->TremeloDepthSlideLength = 0;
    in_pChannel->VibratoDepthSlideLength = 0;
    in_pChannel->AutoPanRateSlideLength = 0;
    in_pChannel->TremeloRateSlideLength = 0;
    in_pChannel->VibratoRateSlideLength = 0;
    in_pChannel->FmTimer = 0;
    in_pChannel->NoiseTimer = 0;
    Sound_SetInstrumentToChannel(in_pChannel, 0U);
}

//----------------------------------------------------------------------------------------------------------------------
u32 ChannelMaskToVoiceMask( FSoundChannel* in_pChannel, u32 in_ChannelMask )
{
    u32 VoiceNumber, Mask;
    u32 i = 0;
    u32 out_VoiceMask = 0;

    while( i < SOUND_CHANNEL_COUNT )
    {
        Mask = 1 << i;
        if( in_ChannelMask & Mask )
        {
            VoiceNumber = in_pChannel->VoiceParams.AssignedVoiceNumber;
            if( VoiceNumber < VOICE_COUNT )
            {
                out_VoiceMask |= 1 << VoiceNumber;
            }
        }
        i++;
        in_pChannel++;
    };
    return out_VoiceMask;
}

//----------------------------------------------------------------------------------------------------------------------
void Sound_LoadAkaoSequence(FAkaoSequence* in_Sequence, s32 in_Mask) {
    FSoundChannel* var_s3;
    FSoundKeymapEntry8* var_a1_2;
    FSoundChannel* var_s0;
    s16 var_a1_3;
    s32 temp_v1;
    s32 temp_v1_2;
    s32 temp_v1_3;
    s32 var_s1_2;
    u16* var_a1;
    u32 var_s1;
    u32 var_s4;
    u32 var_s5;
    u8* temp_v0;
    u8* var_s2;

    g_pActiveMusicContext->SequenceBase = in_Sequence;
    var_s4 = in_Sequence->ChannelEnableMask;
    if (g_pSuspendedMusicContext != NULL) {
        var_s1 = ChannelMaskToVoiceMask(g_pSecondaryMusicChannels, g_pSuspendedMusicContext->ActiveChannelMask);
    } else {
        var_s1 = 0;
    }
    g_Sound_SfxState.KeyOffFlags |= ~var_s1 & (~(g_Sound_Cutscene_StreamState.VoicesInUseFlags | g_Sound_SfxState.ActiveVoiceMask) & 0xFFFFFF);
    g_pActiveMusicContext->PendingKeyOffMask = 0;
    g_pActiveMusicContext->PreventRekeyOnMusicResumeMask = 0;
    if (D_80094FFC & 1) {
        g_pActiveMusicContext->ActiveChannelMask = 0;
        g_pActiveMusicContext->SuspendedChannelMask |= var_s4 & in_Mask;
    } else {
        g_pActiveMusicContext->SuspendedChannelMask = 0;
        g_pActiveMusicContext->ActiveChannelMask |= var_s4 & in_Mask;
    }
    g_pActiveMusicContext->KeyedMask = in_Sequence->KeyedMask;
    g_pActiveMusicContext->AllocatedVoiceMask = in_Sequence->AllocatedVoiceMask;
    g_pActiveMusicContext->StatusFlags &= ~0x33;
    temp_v1 = in_Sequence->PatchRegionOffset;
    var_a1 = NULL;
    if (temp_v1 != 0) {
        var_a1 = (u16*)((u8*)in_Sequence + temp_v1 + 0x30);
    }
    g_pActiveMusicContext->SequencePatchTable = var_a1;
    temp_v1_2 = in_Sequence->KeymapRegionOffset;
    var_a1_2 = NULL;
    if (temp_v1_2 != 0) {
        var_a1_2 = (FSoundKeymapEntry8*)((u8*)in_Sequence + temp_v1_2 + 0x34);
    }
    var_s1_2 = 1;
    var_s5 = 0;
    var_s3 = g_ActiveMusicChannels;
    var_s2 = in_Sequence->Payload;
    var_s0 = g_ActiveMusicChannels;
    g_pActiveMusicContext->KeymapTable = var_a1_2;
    g_pActiveMusicContext->SomeIndexRelatedToSpuVoiceInfo = 0;
    D_80090A34 = 1;
    do {
        temp_v1_3 = var_s4 & var_s1_2;
        var_a1_3 = 4;
        if (temp_v1_3 & in_Mask) {
            temp_v0 = &var_s2[*(u16*)var_s2];
            var_s2 += 2;
            var_s3->ProgramCounter = temp_v0;
            if (D_80094FFC & 0x100) {
                var_a1_3 = 0x1E4;
            }
            var_s0->KeyLength = 2;
            var_s0->VolumeBalance = 0x7F00;
            var_s0->Volume = 0x3FFF0000;
            var_s0->VolumeMod = 0x4000;
            var_s0->NoteLength = var_a1_3;
            var_s0->FineTune = 0;
            var_s0->Transpose = 0;
            var_s0->PortamentoSteps = 0;
            var_s0->PitchSlide = 0;
            var_s0->PitchBendSlideTranspose = 0;
            var_s0->PitchSlideStepsCurrent = 0;
            var_s0->FixedNoteLength = 0;
            var_s0->LengthStored = 0;
            var_s0->ChannelPan = 0x8000;
            var_s0->ChannelPanSlideLength = 0;
            var_s0->PortamentoSteps = 0;
            var_s0->VolumeModStepsRemaining = 0;
            var_s0->ChannelVolumeSlideLength = 0;
            var_s0->FinePitchDelta = 0;
            var_s0->KeyOnVolumeSlideLength = 0;
            var_s0->RandomPitchDepth = 0;
            var_s0->Articulation = 0;
            var_s0->AutoPanVolume = 0;
            var_s0->LoopStackTop = 0;
            var_s0->AutoPanDepth = 0;
            var_s0->TremeloDepth = 0;
            var_s0->VibratoDepth = 0;
            var_s0->AutoPanDepthSlideLength = 0;
            var_s0->TremeloDepthSlideLength = 0;
            var_s0->VibratoDepthSlideLength = 0;
            var_s0->UpdateFlags = (s32) (((g_pActiveMusicContext->AllocatedVoiceMask & var_s1_2) == 0) << 6);
            var_s0->AutoPanRateSlideLength = 0;
            var_s0->TremeloRateSlideLength = 0;
            var_s0->VibratoRateSlideLength = 0;
            var_s0->FmTimer = 0;
            var_s0->NoiseTimer = 0;
            Sound_SetInstrumentToChannel(var_s3, 0U);
        } else {
            if (temp_v1_3 != 0) {
                if (!(var_s1_2 & in_Mask)) {
                    var_s2 += 2;
                }
            }
            var_s0->NoteLength = 3;
            var_s0->KeyLength = 1;
            var_s3->ProgramCounter = (u8* ) &g_Sound_ProgramCounter;
            var_s0->VoiceParams.VoiceParamFlags |= 0x4400;
            var_s0->VoiceParams.AdsrUpper = (var_s0->VoiceParams.AdsrUpper & 0xFFE0) | 5;
        }
        var_s0->VoiceParams.AssignedVoiceNumber = 0x18;
        var_s4 &= ~var_s1_2;
        var_s0++;
        var_s3++;
        var_s5 += 1;
        var_s1_2 *= 2;
    } while (var_s5 < 0x20U);
    g_pActiveMusicContext->Tempo = -0x10000;
    g_pActiveMusicContext->TempoUpdate = 1;
    g_pActiveMusicContext->TempoSlideLength = 0;
    g_pActiveMusicContext->RevDepth = 0;
    g_pActiveMusicContext->ReverbDepthSlideLength = 0;
    g_pActiveMusicContext->ReverbDepthSlideStep = 0;
    g_Sound_GlobalFlags.UpdateFlags = 0;
    g_pActiveMusicContext->TimerLowerCurrent = 0;
    g_pActiveMusicContext->TimerLower = 0;
    g_pActiveMusicContext->TimerUpperCurrent = 0;
    g_pActiveMusicContext->TimerTopCurrent = 0;
    g_pActiveMusicContext->NoiseChannelFlags = 0;
    g_pActiveMusicContext->ReverbChannelFlags = 0;
    g_pActiveMusicContext->FmChannelFlags = 0;
    g_pActiveMusicContext->JumpThreshold = 0;
    g_pActiveMusicContext->ActiveNoteMask = 0;
    g_pActiveMusicContext->PendingKeyOnMask = 0;
    g_Sound_GlobalFlags.UpdateFlags |= 0x100;
}

//----------------------------------------------------------------------------------------------------------------------
void Sound_KillMusicContext( FSoundMusicContext* in_Context, FSoundChannel* in_pChannel, u32 in_MusicId )
{
    FSoundChannel* pChannel;
    FSoundMusicContext** ppCurrentChannelContext;
    u32 Count;

    pChannel = in_pChannel;
    if( ( in_Context->ActiveChannelMask != 0 ) && ( ( in_MusicId == MUSIC_ID_ANY ) || ( in_MusicId == in_Context->MusicId ) ) )
    {
        in_Context->PendingKeyOffMask = -1;
        for( Count = SOUND_CHANNEL_COUNT; Count != 0; Count-- )
        {
            pChannel->NoteLength = 3;
            pChannel->KeyLength = 1;
            pChannel->ProgramCounter = (u8*)&g_Sound_ProgramCounter;
            pChannel++;
        };

        ppCurrentChannelContext = g_Sound_VoiceOwnerContexts;
        in_Context->MusicId = 0;
        in_Context->ActiveNoteMask = 0;
        in_Context->PendingKeyOnMask = 0;

        for( Count = 0; Count < VOICE_COUNT; Count++ )
        {
            if( *ppCurrentChannelContext == in_Context )
            {
                *ppCurrentChannelContext = NULL;
                SetVoiceAdsrReleaseRateAndMode( Count, 5, 3U );
            }
            ppCurrentChannelContext++;
        };
    }
}

//----------------------------------------------------------------------------------------------------------------------
#ifndef NON_MATCHING
INCLUDE_ASM("asm/slps_023.64/nonmatchings/system/sound2", Sound_EvictSfxVoice);
#else
#define RELEASE_MODE_PRIORITY   0x40000000
#define RELEASE_MODE_PAIR       0x80000000  // Negative value check

// TODO(jperos): This is *not* a voice mask, the way it's being tested
// Unless it's packed???
void Sound_EvictSfxVoice( u32 in_ChannelIndex, u32 in_VoiceMask )
{
    FSoundChannel* pChannel;
    u32 VoiceBit;
    u32 ActiveVoices;
    u32 MaskedArg;
    u32 UpdateFlags;
    s32 MaxPriority;
    s32 Priority;
    s32 ChannelIdentifier;
    u32 i;

    ActiveVoices = g_Sound_SfxState.ActiveVoiceMask | g_Sound_SfxState.SuspendedVoiceMask;
    MaskedArg = in_VoiceMask & VOICE_MASK_ALL; // Is this shit packed or what...

    if (MaskedArg != 0)
    {
        /* PATH 1: Release voices matching the mask AND channel's unk_Flags filter */
        pChannel = g_SfxSoundChannels;
        VoiceBit = 1 << SOUND_SFX_CHANNEL_START_INDEX;

        for( i = 0; i < SOUND_SFX_CHANNEL_COUNT; i++ )
        {
            if (ActiveVoices & VoiceBit)
            {
                if (pChannel->unk_Flags & in_VoiceMask)
                {
                    UpdateFlags = pChannel->UpdateFlags;

                    if (UpdateFlags & SOUND_CHANNEL_UPDATE_VOICE_ACTIVE)
                    {
                        /* Voice is busy - mark for deferred release */
                        pChannel->UpdateFlags = UpdateFlags | SOUND_CHANNEL_UPDATE_PENDING_RELEASE;
                    }
                    else
                    {
                        /* Voice not busy - release immediately */
                        g_Sound_SfxState.KeyOffFlags |= VoiceBit;
                        Sound_ClearVoiceFromSfxState(pChannel, VoiceBit);
                        pChannel->UpdateFlags = 0;
                    }
                }
            }

            pChannel++;
            VoiceBit <<= 1;
        };
    }
    else if (in_VoiceMask < 0)
    {
        /* PATH 2A: Release stereo voice pair by index */
        pChannel = &g_SfxSoundChannels[in_ChannelIndex];
        VoiceBit = (1 << SOUND_SFX_CHANNEL_START_INDEX) << in_ChannelIndex;

        /* Release left voice */
        if (ActiveVoices & VoiceBit)
        {
            Sound_EvictSfxVoice(pChannel->AkaoProgramIndex, 0);
        }

        VoiceBit <<= 1;
        pChannel++;

        /* Release right voice */
        if (ActiveVoices & VoiceBit)
        {
            Sound_EvictSfxVoice(pChannel->AkaoProgramIndex, 0);
        }

        return;
    }
    else if (in_VoiceMask & RELEASE_MODE_PRIORITY)
    {
        /* PATH 2B: Priority-based voice stealing */

        /* Pass 1: Filter out voices with non-zero unk_Flags */
        pChannel = g_SfxSoundChannels;
        VoiceBit = (1 << SOUND_SFX_CHANNEL_START_INDEX);

        for( i = 0; i < SOUND_SFX_CHANNEL_COUNT; i++ )
        {
            if (pChannel->unk_Flags != 0)
            {
                ActiveVoices &= ~VoiceBit;
            }

            pChannel++;
            VoiceBit <<= 1;
        };

        /* Pass 2: Find maximum priority (lowest importance = steal first) */
        pChannel = g_SfxSoundChannels;
        VoiceBit = 1 << SOUND_SFX_CHANNEL_START_INDEX;
        MaxPriority = 0;

        for( i = 0; i < SOUND_SFX_CHANNEL_COUNT; i++ )
        {
            if (ActiveVoices & VoiceBit)
            {
                Priority = pChannel->Priority;

                if (MaxPriority < Priority)
                {
                    MaxPriority = Priority;
                }
            }

            pChannel++;
            VoiceBit <<= 1;
        };

        /* Pass 3: Release all voices with max priority value */
        pChannel = g_SfxSoundChannels;
        VoiceBit = 1 << SOUND_SFX_CHANNEL_START_INDEX;

        for( i = 0; i < SOUND_SFX_CHANNEL_COUNT; i++ )
        {
            if (ActiveVoices & VoiceBit)
            {
                if (MaxPriority == pChannel->Priority)
                {
                    UpdateFlags = pChannel->UpdateFlags;

                    if (UpdateFlags & SOUND_CHANNEL_UPDATE_VOICE_ACTIVE)
                    {
                        pChannel->UpdateFlags = UpdateFlags | SOUND_CHANNEL_UPDATE_PENDING_RELEASE;
                    }
                    else
                    {
                        g_Sound_SfxState.KeyOffFlags |= VoiceBit;
                        Sound_ClearVoiceFromSfxState(pChannel, VoiceBit);
                        pChannel->UpdateFlags = 0;
                    }
                }
            }

            pChannel++;
            VoiceBit <<= 1;
        };
    }
    else
    {
        /* PATH 3: Release voices by identifier match */
        pChannel = g_SfxSoundChannels;
        VoiceBit = 1 << SOUND_SFX_CHANNEL_START_INDEX;

        for( i = 0; i < SOUND_SFX_CHANNEL_COUNT; i++ )
        {
            if (ActiveVoices & VoiceBit)
            {
                ChannelIdentifier = pChannel->AkaoProgramIndex;

                if (in_ChannelIndex == -1)
                {
                    /* Release all voices with negative identifier */
                    if (ChannelIdentifier < 0)
                    {
                        UpdateFlags = pChannel->UpdateFlags;

                        if (UpdateFlags & SOUND_CHANNEL_UPDATE_VOICE_ACTIVE)
                        {
                            pChannel->UpdateFlags = UpdateFlags | SOUND_CHANNEL_UPDATE_PENDING_RELEASE;
                        }
                        else
                        {
                            g_Sound_SfxState.KeyOffFlags |= VoiceBit;
                            Sound_ClearVoiceFromSfxState(pChannel, VoiceBit);
                            pChannel->UpdateFlags = 0;
                        }
                    }
                }
                else
                {
                    /* Release voices matching specific identifier */
                    if (ChannelIdentifier == in_ChannelIndex)
                    {
                        UpdateFlags = pChannel->UpdateFlags;

                        if (UpdateFlags & SOUND_CHANNEL_UPDATE_VOICE_ACTIVE)
                        {
                            pChannel->UpdateFlags = UpdateFlags | SOUND_CHANNEL_UPDATE_PENDING_RELEASE;
                        }
                        else
                        {
                            g_Sound_SfxState.KeyOffFlags |= VoiceBit;
                            Sound_ClearVoiceFromSfxState(pChannel, VoiceBit);
                            pChannel->UpdateFlags = 0;
                        }
                    }
                }
            }

            pChannel++;
            VoiceBit <<= 1;
        };
    }

    g_Sound_GlobalFlags.UpdateFlags |= SOUND_GLOBAL_UPDATE_NOISE_CLOCK | SOUND_GLOBAL_UPDATE_VOICE_MODES;
}
#endif

//----------------------------------------------------------------------------------------------------------------------
#ifndef NON_MATCHING
INCLUDE_ASM("asm/slps_023.64/nonmatchings/system/sound2", func_8004E7D8);
#else
void func_8004E7D8( FSoundChannel* in_pChannel, FSoundCommandParams* in_pCommandParams, s32 in_Flags, u8* in_ProgramCounter )
{
    s32 SfxChannelCount;
    in_pChannel->AkaoProgramIndex = in_pCommandParams->Param1;
    in_pChannel->unk_Flags = in_pCommandParams->Param2;
    in_pChannel->PanModStepsRemaining = 0;
    in_pChannel->ChannelPanSlideLength = 0;
    in_pChannel->PanMod = ( *( (u8*)( &in_pCommandParams->Param3 ) ) ) << 8;
    in_pChannel->NoteLength = 2;
    in_pChannel->ChannelPan = 0x8000;
    in_pChannel->KeyLength = 1;
    in_pChannel->Type = SOUND_CHANNEL_TYPE_SFX;
    in_pChannel->VolumeModStepsRemaining = 0;
    in_pChannel->Priority = -2;
    in_pChannel->PitchMod = 0;
    in_pChannel->PitchModStepsRemaining = 0;
    in_pChannel->VolumeMod = ( in_pCommandParams->Param4 & 0x7F ) << 8;
    Sound_ResetChannel( in_pChannel, in_ProgramCounter );
    g_Sound_VoiceOwnerContexts[in_pChannel->VoiceParams.AssignedVoiceNumber] = 0;
    SetVoiceAdsrReleaseRateAndMode( (s32)in_pChannel->VoiceParams.AssignedVoiceNumber, 5, 3U );
    g_Sound_SfxState.ActiveVoiceMask |= in_Flags;
    g_Sound_SfxState.KeyOffFlags |= in_Flags;
    in_Flags = ~in_Flags;
    g_Sound_SfxState.KeyOnFlags &= in_Flags;
    g_Sound_SfxState.KeyedFlags &= in_Flags;
    g_Sound_SfxState.NoiseVoiceFlags &= in_Flags;
    g_Sound_SfxState.ReverbVoiceFlags &= in_Flags;
    g_Sound_SfxState.FmVoiceFlags &= in_Flags;
    if( D_80094FFC & ( 1 << 1 ) )
    {
        in_Flags = 1 << SOUND_SFX_CHANNEL_START_INDEX;
        in_pChannel = g_SfxSoundChannels;
        SfxChannelCount = SOUND_SFX_CHANNEL_COUNT;
        do
        {
            if( ( g_Sound_SfxState.ActiveVoiceMask & in_Flags ) && ( !( in_pChannel->unk_Flags & SOUND_CHANNEL_UNK_FLAGS_25 ) ) )
            {
                g_Sound_SfxState.ActiveVoiceMask &= ~in_Flags;
                g_Sound_SfxState.SuspendedVoiceMask |= in_Flags;
            }
            SfxChannelCount--;
            in_pChannel++;
            in_Flags <<= 1;
        } while( SfxChannelCount != 0 );
    }
}
#endif

//----------------------------------------------------------------------------------------------------------------------
void FreeVoiceChannels( FSoundChannel* in_Channel, u32 in_Voice )
{
    u32 VoiceIndex;

    if( in_Voice < VOICE_COUNT )
    {
        VoiceIndex = 0;
        while( VoiceIndex < SOUND_CHANNEL_COUNT )
        {
            if( in_Channel->VoiceParams.AssignedVoiceNumber == in_Voice )
            {
                in_Channel->VoiceParams.AssignedVoiceNumber = VOICE_COUNT;
                g_pActiveMusicContext->ActiveNoteMask &= ~(1 << VoiceIndex);
            }
            in_Channel++;
            VoiceIndex++;
        };
    }
}

//----------------------------------------------------------------------------------------------------------------------
void Sound_PlaySfxProgram( FSoundCommandParams* in_pCommandParams, u8* in_pProgramCounter1, u8* in_pProgramCounter2, s32 in_NoEvict )
{
    FSoundChannel* pChannel;
    u32 VoiceBit;
    s32 slotsRemaining;
    s32 activeVoices;
    
    if( ( in_pProgramCounter1 == 0 ) && ( in_pProgramCounter2 == 0 ) )
    {
        return;
    }
    
    if( !in_NoEvict && in_pCommandParams->Param2 != 0 )
    {
        Sound_EvictSfxVoice( 0, in_pCommandParams->Param2 );
    }

    do
    {
        pChannel = &g_SfxSoundChannels[11];
        VoiceBit = 1 << (SOUND_SFX_CHANNEL_LAST_INDEX - 1);
        activeVoices = ( g_Sound_SfxState.ActiveVoiceMask | g_Sound_SfxState.SuspendedVoiceMask ) | g_Sound_Cutscene_StreamState.VoicesInUseFlags;
        if( ( in_pProgramCounter1 != 0 ) && (in_pProgramCounter2 != 0 ) )
        {
            slotsRemaining = 11; 
            pChannel--;
            VoiceBit = 1 << (SOUND_SFX_CHANNEL_LAST_INDEX - 2);
            while( slotsRemaining != 0 )
            {
                if( !( activeVoices & ( VoiceBit | ( VoiceBit << 1 ) ) ) )
                {
                    break;
                }
                slotsRemaining--;
                pChannel--;
                VoiceBit >>= 1;
                if (slotsRemaining == 0) 
                {
                    break;
                }
            };
        }
        else
        {
            slotsRemaining = 12;
            while( slotsRemaining != 0 )
            {
                if( !( activeVoices & VoiceBit ) )
                {
                    break;
                }
                slotsRemaining--;
                pChannel--;
                VoiceBit >>= 1;
            };
        }
        if (slotsRemaining != 0) 
        {
            break;
        }
        
        Sound_EvictSfxVoice( 0, 1 << 30 );

        if( activeVoices == (g_Sound_SfxState.ActiveVoiceMask | g_Sound_SfxState.SuspendedVoiceMask | g_Sound_Cutscene_StreamState.VoicesInUseFlags) )
        {
            return;
        }
    } while (slotsRemaining == 0);
    
    if( in_pProgramCounter1 != 0 )
    {
        func_8004E7D8( pChannel, in_pCommandParams, VoiceBit, in_pProgramCounter1 );
        FreeVoiceChannels( g_ActiveMusicChannels, pChannel->VoiceParams.AssignedVoiceNumber );
    }
    if( in_pProgramCounter2 )
    {
        if( in_pProgramCounter1 != 0 )
        {
            pChannel++;
            VoiceBit <<= 1;
        }
        func_8004E7D8( pChannel, in_pCommandParams, VoiceBit, in_pProgramCounter2 );
        FreeVoiceChannels( g_ActiveMusicChannels, pChannel->VoiceParams.AssignedVoiceNumber );
        if( in_pProgramCounter1 != 0 )
        {
            pChannel->UpdateFlags |= SOUND_CHANNEL_UPDATE_STEREO_LINKED;
        }
    }
    g_Sound_GlobalFlags.UpdateFlags |= SOUND_GLOBAL_UPDATE_NOISE_CLOCK | SOUND_GLOBAL_UPDATE_VOICE_MODES;
}

//----------------------------------------------------------------------------------------------------------------------
void Sound_GetProgramCounters( u8** out_ProgramCounter1, u8** out_ProgramCounter2, int in_SfxIndex )
{
    in_SfxIndex &= 0x3FF;
    in_SfxIndex <<= 1;

    *out_ProgramCounter1 = g_Sound_Sfx_ProgramOffsets[in_SfxIndex] != 0xFFFF
        ? g_Sound_Sfx_ProgramData + g_Sound_Sfx_ProgramOffsets[in_SfxIndex]
        : NULL;

    ++in_SfxIndex;

    *out_ProgramCounter2 = g_Sound_Sfx_ProgramOffsets[in_SfxIndex] != 0xFFFF
        ? g_Sound_Sfx_ProgramData  + g_Sound_Sfx_ProgramOffsets[in_SfxIndex]
        : NULL;
}

//----------------------------------------------------------------------------------------------------------------------
// Unknown exactly how this functions but it is setting bits 0 and 1 to each channel in the incoming struct's flags
void Sound_MarkActiveChannelsVolumeDirty( FSoundMusicContext* in_pContext, FSoundChannel* in_pChannel )
{
    u32 ActiveChannelMask;
    u32 Flags;
    u32 Mask;

    ActiveChannelMask = in_pContext->ActiveChannelMask;
    if( ActiveChannelMask == 0 )
    {
        return;
    }

    Flags = ActiveChannelMask;
    Mask = 1;

    while( Flags != 0 )
    {
        if( Flags & Mask )
        {
            in_pChannel->VoiceParams.VoiceParamFlags |= VOICE_PARAM_VOLUME;
            Flags ^= Mask;
        }
        in_pChannel++;
        Mask <<= 1;
    }
}

//----------------------------------------------------------------------------------------------------------------------
void Sound_MarkScheduledSfxChannelsVolumeDirty()
{
    u32 Mask;
    u32 ActiveChannelMask;
    FSoundChannel* pChannel;

    if( g_Sound_SfxState.ActiveVoiceMask == 0 )
    {
        return;
    }

    ActiveChannelMask = g_Sound_SfxState.ActiveVoiceMask;
    pChannel = g_SfxSoundChannels;
    Mask = (1 << 12); // SFX Channels start at channel 12
    while( ActiveChannelMask != 0 )
    {
        if( ActiveChannelMask & Mask )
        {
            ActiveChannelMask ^= Mask;
            pChannel->VoiceParams.VoiceParamFlags |= VOICE_PARAM_VOLUME;
        }
        pChannel++;
        Mask <<= 1;
    };
}

//----------------------------------------------------------------------------------------------------------------------
void Sound_SetMusicSequence( FAkaoSequence* in_Sequence, s32 in_SwapWithSavedState )
{
    FAkaoSequence* previousSequence;
    FSoundChannel* channel;
    FSoundChannel* channelState;
    s32 sequenceOffset;
    s32 channelBit;
    s32 channelsRemaining;
    u32 activeChannelMask;
    u32 voiceMask;

    if( in_SwapWithSavedState == 0 )
    {
        memcpy32( (s32*)&g_SuspendedMusicContext, (s32*)g_pActiveMusicContext, 0x80U );
        memcpy32( (s32*)g_PushedMusicChannels, (s32*)g_ActiveMusicChannels, 0x2480U );
    }
    else
    {
        memswap32( (s32*)&g_SuspendedMusicContext, (s32*)g_pActiveMusicContext, 0x80U );
        memswap32( (s32*)g_PushedMusicChannels, (s32*)g_ActiveMusicChannels, 0x2480U );
    }
    channel = g_ActiveMusicChannels;
    channelsRemaining = 0x20;
    channelBit = 1;
    previousSequence = g_pActiveMusicContext->SequenceBase;
    g_pActiveMusicContext->SequenceBase = in_Sequence;
    g_pActiveMusicContext->PendingKeyOnMask = 0;
    g_pActiveMusicContext->StatusFlags &= ~0x30;
    sequenceOffset = (u8*)in_Sequence - (u8*)previousSequence;
    g_Sound_GlobalFlags.UpdateFlags |= 0x90;
    voiceMask = g_pActiveMusicContext->ActiveChannelMask;
    channelState = g_ActiveMusicChannels;
    g_pActiveMusicContext->SequencePatchTable = (u16*)( (u8*)g_pActiveMusicContext->SequencePatchTable + sequenceOffset );
    g_pActiveMusicContext->KeymapTable = (FSoundKeymapEntry8*)( (u8*)g_pActiveMusicContext->KeymapTable + sequenceOffset );
    g_pActiveMusicContext->PendingKeyOnMask = g_pActiveMusicContext->ActiveNoteMask;
    do
    {
        if( voiceMask & channelBit )
        {
            channel->ProgramCounter = &channel->ProgramCounter[sequenceOffset];
            channelState->Keymap = (u8*)( channelState->Keymap + sequenceOffset );
            channelState->LoopStartPc[0] = (u8*)( channelState->LoopStartPc[0] + sequenceOffset );
            channelState->LoopStartPc[1] = (u8*)( channelState->LoopStartPc[1] + sequenceOffset );
            channelState->LoopStartPc[2] = (u8*)( channelState->LoopStartPc[2] + sequenceOffset );
            channelState->LoopStartPc[3] = (u8*)( channelState->LoopStartPc[3] + sequenceOffset );
            channelState->NoteLength = (u16)( channelState->NoteLength + 2 );
            channelState->KeyLength = (u16)( channelState->KeyLength + 2 );
            channelState->VoiceParams.VoiceParamFlags |= 0x1FF93;
            Sound_MapInstrumentToAltSampleBank( g_pActiveMusicContext->StatusFlags, channel );
        }
        else
        {
            channelState->NoteLength = 4U;
            channelState->KeyLength = 2U;
            channel->ProgramCounter = (u8*)&g_Sound_ProgramCounter;
        }
        channelState->VoiceParams.AssignedVoiceNumber = 0x18;
        channelsRemaining -= 1;
        channelState++;
        channel++;
        channelBit *= 2;
    } while( channelsRemaining != 0 );
    if( g_pSuspendedMusicContext != NULL )
    {
        voiceMask = ChannelMaskToVoiceMask( g_pSecondaryMusicChannels, g_pSuspendedMusicContext->ActiveChannelMask & g_pSuspendedMusicContext->KeyedMask );
    }
    else
    {
        voiceMask = 0;
    }
    g_pActiveMusicContext->PendingKeyOffMask = 0;
    g_SuspendedMusicContext.MusicId = 0;
    g_Sound_SfxState.KeyOffFlags |= ( ~voiceMask & 0xFFFFFF ) & ~( g_Sound_SfxState.ActiveVoiceMask | g_Sound_Cutscene_StreamState.VoicesInUseFlags );
    g_Sound_GlobalFlags.UpdateFlags |= 0x100;
    if( D_80094FFC & 1 )
    {
        activeChannelMask = g_pActiveMusicContext->ActiveChannelMask;
        g_pActiveMusicContext->ActiveChannelMask = 0;
        g_pActiveMusicContext->SuspendedChannelMask = activeChannelMask;
    }
}
