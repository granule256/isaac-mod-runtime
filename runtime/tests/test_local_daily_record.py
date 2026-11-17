"""Host tests for the per-profile local daily challenge record codec."""

import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

DRIVER = textwrap.dedent(
    r"""
    #include "application/game/local_daily_record.hpp"

    #include <array>
    #include <cstddef>
    #include <cstdint>
    #include <cstdio>
    #include <cstring>
    #include <map>
    #include <string>
    #include <string_view>

    using isaac::runtime::ISaveFilePort;
    using isaac::runtime::Status;
    using isaac::runtime::StatusCode;
    using isaac::runtime::local_daily::LoadRecord;
    using isaac::runtime::local_daily::Record;
    using isaac::runtime::local_daily::SaveRecord;
    using isaac::runtime::local_daily::ValidDate;

    namespace {

    constexpr std::size_t kMagicOffset = 0;
    constexpr std::size_t kVersionOffset = 8;
    constexpr std::size_t kDateOffset = 10;
    constexpr std::size_t kFlagsOffset = 14;
    constexpr std::size_t kScoreOffset = 15;
    constexpr std::size_t kChecksumOffset = kScoreOffset + 0x140;
    constexpr std::size_t kFileSize = kChecksumOffset + 4;
    constexpr std::uint8_t kAttemptedFlag = 1;
    constexpr std::uint8_t kHasScoreFlag = 2;

    int failures = 0;

    void Check(bool condition, const char* what) {
        if (!condition) {
            std::printf("FAILED_CHECK %s\n", what);
            ++failures;
        }
    }

    struct FakeSaveFilePort final : ISaveFilePort {
        std::map<std::string, std::string> files;
        std::string lastRead;
        std::string lastWrite;
        Status readFailure{StatusCode::Ok};
        Status writeFailure{StatusCode::Ok};
        unsigned reads{};
        unsigned writes{};

        Status Read(std::string_view name, char* out, std::size_t capacity,
                    std::size_t* size) noexcept override {
            ++reads;
            lastRead = std::string(name);
            if (!readFailure.ok()) {
                return readFailure;
            }
            const auto hit = files.find(std::string(name));
            if (hit == files.end()) {
                if (size != nullptr) {
                    *size = 0;
                }
                return Status{StatusCode::NotFound};
            }
            if (size != nullptr) {
                *size = hit->second.size();
            }
            if (hit->second.size() > capacity) {
                return Status{StatusCode::CapacityExceeded};
            }
            std::memcpy(out, hit->second.data(), hit->second.size());
            return Status::Ok();
        }

        Status Write(std::string_view name, std::string_view data) noexcept override {
            ++writes;
            lastWrite = std::string(name);
            if (!writeFailure.ok()) {
                return writeFailure;
            }
            files[std::string(name)] = std::string(data);
            return Status::Ok();
        }

        Status Remove(std::string_view) noexcept override {
            return Status::Ok();
        }

        Status Exists(const char*, bool* exists) noexcept override {
            if (exists != nullptr) {
                *exists = false;
            }
            return Status::Ok();
        }
    };

    bool SameRecord(const Record& left, const Record& right) {
        return left.date == right.date && left.attempted == right.attempted &&
               left.hasScore == right.hasScore && left.score == right.score;
    }

    Record Sentinel() {
        Record value{};
        value.date = 20251231;
        value.attempted = true;
        value.hasScore = true;
        value.score.fill(0xA5);
        return value;
    }

    Record ScoredRecord(std::uint32_t date, std::uint8_t salt) {
        Record value{};
        value.date = date;
        value.attempted = true;
        value.hasScore = true;
        for (std::size_t index = 0; index < value.score.size(); ++index) {
            value.score[index] = static_cast<std::uint8_t>(index * 37u + salt);
        }
        return value;
    }

    std::uint16_t GetLe16(const std::string& bytes, std::size_t offset) {
        return static_cast<std::uint16_t>(
            static_cast<std::uint8_t>(bytes[offset]) |
            (static_cast<std::uint16_t>(static_cast<std::uint8_t>(bytes[offset + 1])) << 8));
    }

    std::uint32_t GetLe32(const std::string& bytes, std::size_t offset) {
        return static_cast<std::uint32_t>(static_cast<std::uint8_t>(bytes[offset])) |
               (static_cast<std::uint32_t>(static_cast<std::uint8_t>(bytes[offset + 1])) << 8) |
               (static_cast<std::uint32_t>(static_cast<std::uint8_t>(bytes[offset + 2])) << 16) |
               (static_cast<std::uint32_t>(static_cast<std::uint8_t>(bytes[offset + 3])) << 24);
    }

    void PutLe16(std::string& bytes, std::size_t offset, std::uint16_t value) {
        bytes[offset] = static_cast<char>(value & 0xFFu);
        bytes[offset + 1] = static_cast<char>((value >> 8) & 0xFFu);
    }

    void PutLe32(std::string& bytes, std::size_t offset, std::uint32_t value) {
        bytes[offset] = static_cast<char>(value & 0xFFu);
        bytes[offset + 1] = static_cast<char>((value >> 8) & 0xFFu);
        bytes[offset + 2] = static_cast<char>((value >> 16) & 0xFFu);
        bytes[offset + 3] = static_cast<char>((value >> 24) & 0xFFu);
    }

    std::uint32_t Crc32(const std::string& bytes, std::size_t size) {
        std::uint32_t crc = 0xFFFFFFFFu;
        for (std::size_t index = 0; index < size; ++index) {
            crc ^= static_cast<std::uint8_t>(bytes[index]);
            for (unsigned bit = 0; bit < 8; ++bit) {
                const std::uint32_t mask = 0u - (crc & 1u);
                crc = (crc >> 1) ^ (0xEDB88320u & mask);
            }
        }
        return ~crc;
    }

    void RefreshChecksum(std::string& bytes) {
        PutLe32(bytes, kChecksumOffset, Crc32(bytes, kChecksumOffset));
    }

    } // namespace

    int main() {
        for (const std::uint32_t date : {
                 20000101u, 20000229u, 20040229u, 20240229u, 24000229u,
                 21000131u, 20230430u, 99991231u}) {
            Check(ValidDate(date), "valid Gregorian date rejected");
        }
        for (const std::uint32_t date : {
                 19991231u, 10000101u, 20000000u, 20001301u, 20000100u,
                 20000230u, 20230229u, 21000229u, 20230431u, 20230001u,
                 20240100u, 100000000u}) {
            Check(!ValidDate(date), "invalid Gregorian date accepted");
        }

        {
            FakeSaveFilePort port{};
            Record out = Sentinel();
            const Record before = out;
            Check(LoadRecord(nullptr, 1, 20260117, &out).code() ==
                      StatusCode::InvalidArgument,
                  "Load with no port must fail");
            Check(SameRecord(out, before), "missing port must not reset output");
            Check(LoadRecord(&port, 0, 20260117, &out).code() ==
                      StatusCode::InvalidArgument,
                  "Load with slot zero must fail");
            Check(LoadRecord(&port, 4, 20260117, &out).code() ==
                      StatusCode::InvalidArgument,
                  "Load with out-of-range slot must fail");
            Check(LoadRecord(&port, 1, 20260117, nullptr).code() ==
                      StatusCode::InvalidArgument,
                  "Load with no output must fail");
            Check(LoadRecord(&port, 1, 20230229, &out).code() ==
                      StatusCode::InvalidArgument,
                  "Load with invalid date must fail");
            Check(SameRecord(out, before), "invalid arguments must not reset output");
        }

        {
            FakeSaveFilePort port{};
            Record out = Sentinel();
            const Status status = LoadRecord(&port, 1, 20260117, &out);
            Check(status.ok(), "missing record must be an empty daily, not an error");
            Check(port.lastRead == "local_daily_1_20260117.bin",
                  "Load must use the dedicated slot/date filename");
            Check(out.date == 20260117, "missing record must carry the requested date");
            Check(!out.attempted && !out.hasScore, "missing record must be unattempted");
            Check(out.score == Record{}.score, "missing record score must be zeroed");
        }

        {
            FakeSaveFilePort port{};
            Record invalid = ScoredRecord(20260117, 1);
            invalid.attempted = false;
            Check(SaveRecord(nullptr, 1, invalid).code() == StatusCode::InvalidArgument,
                  "Save with no port must fail");
            Check(SaveRecord(&port, 0, invalid).code() == StatusCode::InvalidArgument,
                  "Save with slot zero must fail");
            Check(SaveRecord(&port, 4, invalid).code() == StatusCode::InvalidArgument,
                  "Save with out-of-range slot must fail");
            Check(port.writes == 0, "invalid slots must not write");

            invalid.date = 20230229;
            invalid.attempted = true;
            Check(SaveRecord(&port, 1, invalid).code() == StatusCode::InvalidArgument,
                  "Save with invalid date must fail");
            Check(port.writes == 0, "invalid date must not write");

            Record impossible = ScoredRecord(20260117, 2);
            impossible.attempted = false;
            Check(SaveRecord(&port, 1, impossible).code() ==
                      StatusCode::InvalidArgument,
                  "hasScore without attempted must fail");
            Check(port.writes == 0, "invalid flags must not write");
        }

        {
            FakeSaveFilePort port{};
            const Record saved = ScoredRecord(20240229, 3);
            const unsigned readsBefore = port.reads;
            Check(SaveRecord(&port, 2, saved).ok(), "Save must succeed");
            Check(port.reads == readsBefore, "Save must not perform a read");
            Check(port.lastWrite == "local_daily_2_20240229.bin",
                  "Save must use the dedicated slot/date filename");
            const auto hit = port.files.find("local_daily_2_20240229.bin");
            Check(hit != port.files.end(), "Save must write only the dedicated file");
            Check(port.files.size() == 1, "Save must not write an official save file");
            if (hit != port.files.end()) {
                const std::string& bytes = hit->second;
                Check(bytes.size() == kFileSize, "record file must have a fixed size");
                Check(bytes.compare(kMagicOffset, 8, "ISADLY01") == 0,
                      "record file magic must match");
                Check(GetLe16(bytes, kVersionOffset) == 1, "record format version must be 1");
                Check(GetLe32(bytes, kDateOffset) == 20240229,
                      "encoded date must be little-endian");
                Check(static_cast<std::uint8_t>(bytes[kFlagsOffset]) ==
                          (kAttemptedFlag | kHasScoreFlag),
                      "encoded flags must describe the record");
                Check(std::memcmp(bytes.data() + kScoreOffset, saved.score.data(),
                                  saved.score.size()) == 0,
                      "all 320 score bytes must be copied exactly");
                Check(GetLe32(bytes, kChecksumOffset) == Crc32(bytes, kChecksumOffset),
                      "record checksum must cover every preceding byte");
            }

            Record loaded = Sentinel();
            Check(LoadRecord(&port, 2, 20240229, &loaded).ok(),
                  "saved record must load");
            Check(SameRecord(loaded, saved), "320-byte scored record must round-trip");
        }

        {
            FakeSaveFilePort port{};
            Record attempted{};
            attempted.date = 20240301;
            attempted.attempted = true;
            Check(SaveRecord(&port, 3, attempted).ok(),
                  "attempted daily without a score must save");
            const std::string& bytes = port.files["local_daily_3_20240301.bin"];
            Check(static_cast<std::uint8_t>(bytes[kFlagsOffset]) == kAttemptedFlag,
                  "attempted-only flags must omit hasScore");
            Record loaded = Sentinel();
            Check(LoadRecord(&port, 3, 20240301, &loaded).ok(),
                  "attempted-only record must reload");
            Check(loaded.attempted && !loaded.hasScore,
                  "attempted state must survive without a score");
        }

        {
            FakeSaveFilePort port{};
            const Record slotOne = ScoredRecord(20260117, 11);
            Record slotTwoRaw = ScoredRecord(20260117, 77);
            for (std::size_t index = 0; index < slotTwoRaw.score.size(); ++index) {
                slotTwoRaw.score[index] = static_cast<std::uint8_t>(index * 5u + 9u);
            }
            Check(SaveRecord(&port, 1, slotOne).ok(), "save slot one");
            Check(SaveRecord(&port, 2, slotTwoRaw).ok(), "save slot two");
            Check(port.files.count("local_daily_1_20260117.bin") == 1,
                  "slot one must have its own file");
            Check(port.files.count("local_daily_2_20260117.bin") == 1,
                  "slot two must have its own file");

            Record loaded = Sentinel();
            Check(LoadRecord(&port, 1, 20260117, &loaded).ok() &&
                      SameRecord(loaded, slotOne),
                  "slot one must load its own record");
            loaded = Sentinel();
            Check(LoadRecord(&port, 2, 20260117, &loaded).ok() &&
                      SameRecord(loaded, slotTwoRaw),
                  "slot two must load its own record");
        }

        {
            FakeSaveFilePort port{};
            const Record saved = ScoredRecord(20260117, 19);
            Check(SaveRecord(&port, 1, saved).ok(), "save corruption fixture");
            const std::string pristine = port.files["local_daily_1_20260117.bin"];
            const Record before = Sentinel();

            std::string bytes = pristine;
            bytes[kChecksumOffset] ^= 0x80;
            port.files["local_daily_1_20260117.bin"] = bytes;
            Record out = before;
            Check(LoadRecord(&port, 1, 20260117, &out).code() == StatusCode::Corrupted,
                  "corrupt checksum must fail");
            Check(SameRecord(out, before), "corrupt checksum must not reset output");

            bytes = pristine;
            PutLe32(bytes, kDateOffset, 20230229u);
            RefreshChecksum(bytes);
            port.files["local_daily_1_20260117.bin"] = bytes;
            out = before;
            Check(LoadRecord(&port, 1, 20260117, &out).code() == StatusCode::Corrupted,
                  "invalid checksum-valid date must fail");
            Check(SameRecord(out, before), "corrupt date must not reset output");

            bytes = pristine;
            bytes[kFlagsOffset] = static_cast<char>(0x04);
            RefreshChecksum(bytes);
            port.files["local_daily_1_20260117.bin"] = bytes;
            out = before;
            Check(LoadRecord(&port, 1, 20260117, &out).code() == StatusCode::Corrupted,
                  "unknown flags must fail");
            Check(SameRecord(out, before), "corrupt flags must not reset output");

            bytes = pristine;
            bytes[kFlagsOffset] = static_cast<char>(kHasScoreFlag);
            RefreshChecksum(bytes);
            port.files["local_daily_1_20260117.bin"] = bytes;
            out = before;
            Check(LoadRecord(&port, 1, 20260117, &out).code() == StatusCode::Corrupted,
                  "hasScore without attempted must be corrupt");
            Check(SameRecord(out, before), "inconsistent flags must not reset output");

            bytes = pristine;
            bytes[kMagicOffset] ^= 0x01;
            RefreshChecksum(bytes);
            port.files["local_daily_1_20260117.bin"] = bytes;
            out = before;
            Check(LoadRecord(&port, 1, 20260117, &out).code() == StatusCode::Corrupted,
                  "wrong magic must fail even with a valid checksum");
            Check(SameRecord(out, before), "wrong magic must not reset output");

            bytes = pristine;
            PutLe16(bytes, kVersionOffset, 2);
            RefreshChecksum(bytes);
            port.files["local_daily_1_20260117.bin"] = bytes;
            out = before;
            Check(LoadRecord(&port, 1, 20260117, &out).code() == StatusCode::Corrupted,
                  "unknown format version must fail");
            Check(SameRecord(out, before), "unknown version must not reset output");

            bytes = pristine;
            bytes.pop_back();
            port.files["local_daily_1_20260117.bin"] = bytes;
            out = before;
            Check(LoadRecord(&port, 1, 20260117, &out).code() == StatusCode::Corrupted,
                  "short record must fail as corrupt");
            Check(SameRecord(out, before), "short record must not reset output");
        }

        {
            FakeSaveFilePort port{};
            port.files["local_daily_1_20260117.bin"] = std::string(kFileSize + 1, '\0');
            Record out = Sentinel();
            const Record before = out;
            Check(LoadRecord(&port, 1, 20260117, &out).code() ==
                      StatusCode::CapacityExceeded,
                  "oversized record must preserve the port failure");
            Check(SameRecord(out, before), "oversized record must not reset output");
        }

        {
            FakeSaveFilePort port{};
            Record out = Sentinel();
            const Record before = out;
            port.readFailure = Status{StatusCode::IoFailure};
            Check(LoadRecord(&port, 1, 20260117, &out).code() == StatusCode::IoFailure,
                  "read failure must be propagated");
            Check(SameRecord(out, before), "read failure must not reset output");
        }

        {
            FakeSaveFilePort port{};
            const Record saved = ScoredRecord(20260117, 23);
            Check(SaveRecord(&port, 1, saved).ok(), "prepare save failure fixture");
            const std::string original = port.files["local_daily_1_20260117.bin"];
            port.writeFailure = Status{StatusCode::Rejected};
            Record changed = saved;
            changed.score.fill(0xEE);
            Check(SaveRecord(&port, 1, changed).code() == StatusCode::Rejected,
                  "write failure must be propagated unchanged");
            Check(port.files["local_daily_1_20260117.bin"] == original,
                  "failed atomic write must leave the prior record intact");
        }

        return failures == 0 ? 0 : 1;
    }
    """
)


class LocalDailyRecordTests(unittest.TestCase):
    def test_date_validation_storage_and_corruption_contracts(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="local-daily-record-") as folder:
            folder = Path(folder)
            source = folder / "driver.cpp"
            binary = folder / "driver"
            source.write_text(DRIVER)
            built = subprocess.run(
                [
                    compiler,
                    "-std=c++20",
                    "-fno-exceptions",
                    "-fno-rtti",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(SRC),
                    str(source),
                    str(SRC / "application/game/local_daily_record.cpp"),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


if __name__ == "__main__":
    unittest.main()
