from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RuntimePerfSnapshotTests(unittest.TestCase):
    def run_driver(self, text):
        with tempfile.TemporaryDirectory(prefix='isaac-perf-snapshot-') as folder:
            source = Path(folder) / 'test.cpp'
            binary = Path(folder) / 'test'
            source.write_text(text)
            result = subprocess.run(
                [shutil.which('clang++') or 'g++', '-std=c++17', '-Wall', '-Wextra',
                 '-Werror', '-I', str(ROOT / 'runtime/src'), str(source), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_loaded_mod_event_pairs_are_not_lost(self):
        self.run_driver(r'''
#include "interfaces/lua/runtime_perf.hpp"
#include <cassert>
int main() {
    using namespace isaac::runtime;
    RuntimePerfCallbackBucket buckets[kRuntimePerfBucketCount]{};
    std::uint64_t overflow = 0;
    for (unsigned owner = 1; owner <= 25; ++owner)
        for (unsigned event = 0; event < 8; ++event)
            (void)RecordRuntimePerfCallbackSample(buckets, kRuntimePerfBucketCount,
                RuntimePerfCallbackKey(event, owner, 1), owner, &overflow);
    assert(overflow == 0 && "normal mod/event workload loses callback attribution");
    unsigned total = 0;
    for (const auto& bucket : buckets) total += bucket.count;
    assert(total == 200);
}
''')

    def test_snapshot_layout_and_complete_copy(self):
        self.run_driver(r'''
#include "interfaces/lua/runtime_perf_snapshot.hpp"
#include <cassert>
int main() {
    using namespace isaac::runtime;
    RuntimePerfCallbackBucket callbacks[kRuntimePerfBucketCount]{};
    RuntimePerfCallbackBucket apis[kRuntimePerfApiBucketCount]{};
    callbacks[511].key = 123; callbacks[511].count = 42;
    apis[511].key = 456; apis[511].ticks = 99;
    RuntimePerfSnapshot snapshot{};
    RuntimePerfSnapshotHeader header{};
    header.sequence = 17; header.callbackCalls = 42;
    header.flags = kRuntimePerfSnapshotTiming;
    CopyRuntimePerfSnapshot(snapshot, header, callbacks, apis);
    assert(snapshot.header.magic == kRuntimePerfSnapshotMagic);
    assert(snapshot.header.version == 1);
    assert(snapshot.header.headerBytes == sizeof(header));
    assert(snapshot.header.bucketBytes == sizeof(RuntimePerfCallbackBucket));
    assert(snapshot.header.sequence == 17 && snapshot.header.callbackCalls == 42);
    assert(snapshot.callbacks[511].count == 42 && snapshot.apis[511].ticks == 99);
    callbacks[511].count = 100;
    assert(snapshot.callbacks[511].count == 42);
}
''')

    def test_disabled_attribution_does_not_touch_the_table(self):
        self.run_driver(r'''
#include "interfaces/lua/runtime_perf.hpp"
#include <cassert>
int main() {
    using namespace isaac::runtime;
    RuntimePerfCallbackBucket buckets[4]{};
    std::uint64_t overflow = 9;
    assert(!RecordRuntimePerfCallbackSample(buckets,4,1,10,&overflow,false));
    assert(buckets[0].count == 0 && overflow == 9);
    assert(RecordRuntimePerfCallbackSample(buckets,4,1,10,&overflow,true));
}
''')

    def test_attribution_deadline_expires_without_a_stop_request(self):
        self.run_driver(r'''
#include "interfaces/lua/runtime_perf_snapshot.hpp"
#include <cassert>
int main() {
    using isaac::runtime::RuntimePerfAttributionActive;
    assert(!RuntimePerfAttributionActive(0, 100));
    assert(!RuntimePerfAttributionActive(200, 0));
    assert(RuntimePerfAttributionActive(200, 199));
    assert(!RuntimePerfAttributionActive(200, 200));
    assert(!RuntimePerfAttributionActive(200, 201));
}
''')
