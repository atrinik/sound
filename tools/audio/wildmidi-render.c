#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <wildmidi_lib.h>

#define RENDERER_VERSION "atrinik-wildmidi-render 1"
#define BUFFER_SIZE 65536U

static void write_u16le(unsigned char *buffer, uint16_t value)
{
    buffer[0] = (unsigned char)(value & 0xffU);
    buffer[1] = (unsigned char)(value >> 8);
}

static void write_u32le(unsigned char *buffer, uint32_t value)
{
    buffer[0] = (unsigned char)(value & 0xffU);
    buffer[1] = (unsigned char)((value >> 8) & 0xffU);
    buffer[2] = (unsigned char)((value >> 16) & 0xffU);
    buffer[3] = (unsigned char)(value >> 24);
}

static int write_header(FILE *stream, uint32_t sample_rate, uint32_t data_size)
{
    unsigned char header[44] = {0};

    memcpy(header, "RIFF", 4);
    write_u32le(header + 4, data_size + 36U);
    memcpy(header + 8, "WAVEfmt ", 8);
    write_u32le(header + 16, 16U);
    write_u16le(header + 20, 1U);
    write_u16le(header + 22, 2U);
    write_u32le(header + 24, sample_rate);
    write_u32le(header + 28, sample_rate * 4U);
    write_u16le(header + 32, 4U);
    write_u16le(header + 34, 16U);
    memcpy(header + 36, "data", 4);
    write_u32le(header + 40, data_size);
    return fwrite(header, 1, sizeof(header), stream) == sizeof(header) ? 0 : -1;
}

static int fail(const char *message)
{
    const char *detail = WildMidi_GetError();
    fprintf(stderr, "%s%s%s\n", message, detail != NULL ? ": " : "",
            detail != NULL ? detail : "");
    return 1;
}

int main(int argc, char **argv)
{
    const char *config = NULL;
    const char *output = NULL;
    const char *input = NULL;
    unsigned long rate = 0;
    midi *handle = NULL;
    FILE *stream = NULL;
    int8_t *buffer = NULL;
    uint64_t total = 0;
    int status = 1;

    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts(RENDERER_VERSION);
        return 0;
    }
    if (argc != 8 || strcmp(argv[1], "-c") != 0 ||
            strcmp(argv[3], "-r") != 0 || strcmp(argv[5], "-o") != 0) {
        fprintf(stderr, "usage: %s -c CONFIG -r RATE -o OUTPUT INPUT\n", argv[0]);
        return 2;
    }
    config = argv[2];
    output = argv[6];
    input = argv[7];
    errno = 0;
    rate = strtoul(argv[4], NULL, 10);
    if (errno != 0 || rate < 8000UL || rate > 65535UL) {
        fputs("invalid sample rate\n", stderr);
        return 2;
    }
    if (WildMidi_Init(config, (uint16_t)rate, 0) != 0) {
        return fail("cannot initialize WildMIDI");
    }
    handle = WildMidi_Open(input);
    if (handle == NULL) {
        fail("cannot open MIDI input");
        goto cleanup;
    }
    stream = fopen(output, "wb+");
    if (stream == NULL || write_header(stream, (uint32_t)rate, 0) != 0) {
        perror("cannot create WAV output");
        goto cleanup;
    }
    buffer = malloc(BUFFER_SIZE);
    if (buffer == NULL) {
        fputs("cannot allocate render buffer\n", stderr);
        goto cleanup;
    }
    for (;;) {
        int produced = WildMidi_GetOutput(handle, buffer, BUFFER_SIZE);
        if (produced < 0) {
            fail("cannot render MIDI input");
            goto cleanup;
        }
        if (produced == 0) {
            break;
        }
        total += (uint32_t)produced;
        if (total > UINT32_MAX - 36U ||
                fwrite(buffer, 1, (size_t)produced, stream) != (size_t)produced) {
            fputs("WAV output is too large or could not be written\n", stderr);
            goto cleanup;
        }
    }
    if (fseek(stream, 0, SEEK_SET) != 0 ||
            write_header(stream, (uint32_t)rate, (uint32_t)total) != 0 ||
            fclose(stream) != 0) {
        stream = NULL;
        fputs("cannot finalize WAV output\n", stderr);
        goto cleanup;
    }
    stream = NULL;
    status = 0;

cleanup:
    free(buffer);
    if (stream != NULL) {
        fclose(stream);
    }
    if (handle != NULL) {
        WildMidi_Close(handle);
    }
    WildMidi_Shutdown();
    return status;
}
