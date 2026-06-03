/* NitoBot holographic memory — native C reference encoder (HDC/VSA, v1).
 *
 * Self-contained (bundled SHA-256, no deps). Produces byte-identical hypervectors to
 * memory.py — proof that the encoding is a portable, language-agnostic spec. Also the
 * fast path for edge: pure integer/bitwise, runs on a microcontroller.
 *
 *   cc -O2 -o holo native/holo.c
 *   ./holo "nito" "el conejo"        # -> one hex hypervector per line
 *   ./holo --bench                   # encode throughput
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* ---------- SHA-256 (FIPS 180-4) ---------- */
typedef struct { uint32_t h[8]; uint64_t len; uint8_t buf[64]; size_t n; } sha;
static const uint32_t K[64] = {
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#define ROR(x,n) (((x)>>(n))|((x)<<(32-(n))))
static void sha_block(sha *s, const uint8_t *p) {
    uint32_t w[64], a,b,c,d,e,f,g,h,t1,t2; int i;
    for (i=0;i<16;i++) w[i]=(p[i*4]<<24)|(p[i*4+1]<<16)|(p[i*4+2]<<8)|p[i*4+3];
    for (i=16;i<64;i++){ uint32_t s0=ROR(w[i-15],7)^ROR(w[i-15],18)^(w[i-15]>>3);
        uint32_t s1=ROR(w[i-2],17)^ROR(w[i-2],19)^(w[i-2]>>10); w[i]=w[i-16]+s0+w[i-7]+s1; }
    a=s->h[0];b=s->h[1];c=s->h[2];d=s->h[3];e=s->h[4];f=s->h[5];g=s->h[6];h=s->h[7];
    for (i=0;i<64;i++){ uint32_t S1=ROR(e,6)^ROR(e,11)^ROR(e,25), ch=(e&f)^(~e&g);
        t1=h+S1+ch+K[i]+w[i]; uint32_t S0=ROR(a,2)^ROR(a,13)^ROR(a,22), mj=(a&b)^(a&c)^(b&c);
        t2=S0+mj; h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2; }
    s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha_init(sha *s){ uint32_t iv[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
    0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}; memcpy(s->h,iv,32); s->len=0; s->n=0; }
static void sha_update(sha *s,const uint8_t *p,size_t n){ s->len+=n;
    while(n){ size_t t=64-s->n; if(t>n)t=n; memcpy(s->buf+s->n,p,t); s->n+=t; p+=t; n-=t;
        if(s->n==64){ sha_block(s,s->buf); s->n=0; } } }
static void sha_final(sha *s,uint8_t out[32]){ uint64_t bits=s->len*8; uint8_t pad=0x80;
    sha_update(s,&pad,1); pad=0; while(s->n!=56) sha_update(s,&pad,1);
    uint8_t L[8]; for(int i=0;i<8;i++) L[i]=bits>>(56-8*i); sha_update(s,L,8);
    for(int i=0;i<8;i++){ out[i*4]=s->h[i]>>24;out[i*4+1]=s->h[i]>>16;out[i*4+2]=s->h[i]>>8;out[i*4+3]=s->h[i]; } }
static void sha256(const uint8_t *d,size_t n,uint8_t out[32]){ sha s; sha_init(&s); sha_update(&s,d,n); sha_final(&s,out); }

/* ---------- HDC encoder (matches memory.py exactly) ---------- */
#define DIM 8192
#define BYTES (DIM/8)
#define NGRAM 3
static const char *SEED = "nito-hdc-v1";

static uint8_t symbits[256][DIM];
static int symset[256];
static uint8_t *symbol(int b){
    if (symset[b]) return symbits[b];
    uint8_t material[BYTES]; size_t off=0; uint32_t ctr=0;
    size_t sl=strlen(SEED);
    while (off<BYTES){
        uint8_t in[64]; size_t il=0;
        memcpy(in,SEED,sl); il=sl; in[il++]=(uint8_t)b;            /* SEED || b || u32be(ctr) — ctr starts at 0 */
        in[il++]=ctr>>24; in[il++]=ctr>>16; in[il++]=ctr>>8; in[il++]=ctr;
        uint8_t dig[32]; sha256(in,il,dig);
        size_t take=(BYTES-off<32)?(BYTES-off):32; memcpy(material+off,dig,take); off+=take; ctr++;
    }
    for (int j=0;j<DIM;j++) symbits[b][j]=(material[j>>3]>>(7-(j&7)))&1;  /* MSB-first */
    symset[b]=1; return symbits[b];
}

static void encode(const uint8_t *data,size_t n,uint8_t out[BYTES]){
    if (n==0){ static const uint8_t z[1]={0}; data=z; n=1; }
    int grams = (n>=NGRAM)?(int)(n-NGRAM+1):1;
    static int counts[DIM]; memset(counts,0,sizeof(counts));
    for (int gi=0; gi<grams; gi++){
        static uint8_t gv[DIM]; memset(gv,0,DIM);
        for (int pos=0; pos<NGRAM; pos++){
            size_t idx=(size_t)gi+pos; if (idx>=n) break;          /* short text: fewer symbols */
            uint8_t *s=symbol(data[idx]);
            for (int i=0;i<DIM;i++){ int src=i-pos; if(src<0)src+=DIM; gv[i]^=s[src]; }  /* roll(pos) then XOR */
        }
        for (int i=0;i<DIM;i++) counts[i]+=gv[i];
    }
    memset(out,0,BYTES);
    for (int i=0;i<DIM;i++) if (counts[i]*2>grams) out[i>>3]|=1<<(7-(i&7));  /* majority, MSB-first */
}

int main(int argc,char**argv){
    if (argc>=2 && strcmp(argv[1],"--bench")==0){
        const char *m="the quick brown fox jumps over the lazy dog and writes a discord message";
        uint8_t out[BYTES]; int N=100000;
        clock_t t=clock(); for(int i=0;i<N;i++) encode((const uint8_t*)m,strlen(m),out);
        double us=(double)(clock()-t)/CLOCKS_PER_SEC/N*1e6;
        printf("encode: %.2f us/message\n", us); return 0;
    }
    for (int a=1;a<argc;a++){
        uint8_t out[BYTES]; encode((const uint8_t*)argv[a],strlen(argv[a]),out);
        for (int i=0;i<BYTES;i++) printf("%02x",out[i]); printf("\n");
    }
    return 0;
}
