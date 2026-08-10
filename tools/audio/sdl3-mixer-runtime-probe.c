#include <SDL3/SDL.h>
#include <SDL3_mixer/SDL_mixer.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DECODE_BUFFER_BYTES (64 * 1024)
#define MAX_DECODED_BYTES (256 * 1024 * 1024)

static int fail(const char *message)
{
    fprintf(stderr, "SDL3_mixer Opus probe failed: %s: %s\n", message, SDL_GetError());
    return 1;
}

int main(int argc, char **argv)
{
    MIX_AudioDecoder *decoder = NULL;
    MIX_Mixer *mixer = NULL;
    MIX_Audio *audio = NULL;
    MIX_Track *track = NULL;
    SDL_AudioSpec output_spec = { SDL_AUDIO_S16, 2, 48000 };
    uint8_t buffer[DECODE_BUFFER_BYTES];
    size_t total = 0;
    bool nonzero = false;
    bool opus_decoder = false;
    uint64_t expected_frames;
    uint64_t expected_bytes;
    char *number_end = NULL;
    int result = 1;

    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts("atrinik-sound-sdl3-mixer-probe 2");
        return 0;
    }
    if (argc != 4) {
        fprintf(stderr, "usage: %s OPUS_FILE EXPECTED_FRAMES BEHAVIORS\n", argv[0]);
        return 2;
    }
    expected_frames = strtoull(argv[2], &number_end, 10);
    if (number_end == argv[2] || *number_end != '\0' || expected_frames == 0 ||
            expected_frames > MAX_DECODED_BYTES / 4) {
        fprintf(stderr, "invalid expected frame count: %s\n", argv[2]);
        return 2;
    }
    expected_bytes = expected_frames * 4;
    if (!SDL_Init(0)) {
        return fail("SDL_Init");
    }
    if (!MIX_Init()) {
        result = fail("MIX_Init");
        goto done;
    }
    for (int i = 0; i < MIX_GetNumAudioDecoders(); ++i) {
        const char *name = MIX_GetAudioDecoder(i);
        if (name != NULL && strcmp(name, "OPUS") == 0) {
            opus_decoder = true;
            break;
        }
    }
    if (!opus_decoder) {
        SDL_SetError("OPUS decoder is unavailable");
        result = fail("decoder enumeration");
        goto done;
    }
    decoder = MIX_CreateAudioDecoder(argv[1], 0);
    if (decoder == NULL) {
        result = fail("MIX_CreateAudioDecoder");
        goto done;
    }
    for (;;) {
        const int decoded = MIX_DecodeAudio(decoder, buffer, sizeof(buffer), &output_spec);
        if (decoded < 0) {
            result = fail("MIX_DecodeAudio");
            goto done;
        }
        if (decoded == 0) {
            break;
        }
        if (total > MAX_DECODED_BYTES - (size_t)decoded) {
            SDL_SetError("decoded PCM exceeds the 256 MiB safety bound");
            result = fail("decoded length");
            goto done;
        }
        total += (size_t)decoded;
        for (int i = 0; i < decoded; ++i) {
            nonzero = nonzero || buffer[i] != 0;
        }
    }
    if (total == 0 || !nonzero) {
        SDL_SetError("decoded PCM is empty or silent");
        result = fail("decoded content");
        goto done;
    }
    if (total % 4 != 0 || total + (48000 * 4) < expected_bytes ||
            total > expected_bytes + (48000 * 4)) {
        SDL_SetError("decoded PCM length differs from the expected duration by more than one second");
        result = fail("decoded length");
        goto done;
    }

    if (strcmp(argv[3], "none") != 0) {
        const Sint64 expected_duration = (Sint64)expected_frames;

        mixer = MIX_CreateMixer(&output_spec);
        if (mixer == NULL) {
            result = fail("MIX_CreateMixer");
            goto done;
        }
        audio = MIX_LoadAudio(mixer, argv[1], false);
        if (audio == NULL) {
            result = fail("MIX_LoadAudio");
            goto done;
        }
        track = MIX_CreateTrack(mixer);
        if (track == NULL || !MIX_SetTrackAudio(track, audio) || !MIX_PlayTrack(track, 0)) {
            result = fail("track setup");
            goto done;
        }
        if (MIX_Generate(mixer, buffer, sizeof(buffer)) <= 0) {
            result = fail("initial MIX_Generate");
            goto done;
        }
        if (strstr(argv[3], "seek") != NULL) {
            const Sint64 target = expected_duration / 2;
            if (!MIX_SetTrackPlaybackPosition(track, target) ||
                    MIX_Generate(mixer, buffer, sizeof(buffer)) <= 0 ||
                    MIX_GetTrackPlaybackPosition(track) < target) {
                result = fail("seek behavior");
                goto done;
            }
        }
        if (strstr(argv[3], "stop") != NULL) {
            if (!MIX_StopTrack(track, 0) || MIX_TrackPlaying(track)) {
                result = fail("stop behavior");
                goto done;
            }
        }
        if (strstr(argv[3], "loop") != NULL) {
            uint64_t frames_to_generate = expected_frames + (sizeof(buffer) / 4);
            if (!MIX_PlayTrack(track, 0) || !MIX_SetTrackLoops(track, 1)) {
                result = fail("loop setup");
                goto done;
            }
            while (frames_to_generate > 0) {
                const size_t frames = frames_to_generate > sizeof(buffer) / 4
                    ? sizeof(buffer) / 4 : (size_t)frames_to_generate;
                if (MIX_Generate(mixer, buffer, (int)(frames * 4)) <= 0) {
                    result = fail("loop MIX_Generate");
                    goto done;
                }
                frames_to_generate -= frames;
            }
            if (!MIX_TrackPlaying(track)) {
                SDL_SetError("track stopped instead of entering its second loop iteration");
                result = fail("loop behavior");
                goto done;
            }
        }
    }
    printf("decoded %zu bytes through SDL3_mixer OPUS\n", total);
    result = 0;

done:
    MIX_DestroyAudio(audio);
    MIX_DestroyMixer(mixer);
    MIX_DestroyAudioDecoder(decoder);
    MIX_Quit();
    SDL_Quit();
    return result;
}
