#include <SDL3/SDL.h>
#include <SDL3_mixer/SDL_mixer.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
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
    SDL_AudioSpec output_spec = { SDL_AUDIO_S16, 2, 48000 };
    uint8_t buffer[DECODE_BUFFER_BYTES];
    size_t total = 0;
    bool nonzero = false;
    bool opus_decoder = false;
    int result = 1;

    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts("atrinik-sound-sdl3-mixer-probe 1");
        return 0;
    }
    if (argc != 2) {
        fprintf(stderr, "usage: %s OPUS_FILE\n", argv[0]);
        return 2;
    }
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
    printf("decoded %zu bytes through SDL3_mixer OPUS\n", total);
    result = 0;

done:
    MIX_DestroyAudioDecoder(decoder);
    MIX_Quit();
    SDL_Quit();
    return result;
}
