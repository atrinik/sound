#define _GNU_SOURCE

#include <stdlib.h>
#include <time.h>

/* TiMidity++ 2.14.0 seeds libc's synthesis RNG with time(NULL) and exposes no
 * seed option. Supply a fixed sequence without changing the host clock. */
static unsigned int rng_state = 1;

void srand(unsigned int seed)
{
    (void)seed;
    rng_state = 0x41545249U;
}

int rand(void)
{
    rng_state = rng_state * 1103515245U + 12345U;
    return (int)(rng_state & RAND_MAX);
}

time_t time(time_t *result)
{
    const time_t fixed = 946684800;

    if (result != NULL) {
        *result = fixed;
    }
    return fixed;
}
