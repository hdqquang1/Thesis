"""Tests for the wire protocol encode/decode functions.

Verifies both round-trip correctness (decode inverts encode) and absolute
wire-format guarantees (exact byte sizes and layout), since the C++ UE5
implementation must agree byte-for-byte with this one.
"""

import struct

import pytest
import numpy as np

from vrseg import protocol

# Expected wire sizes. These are contract values shared with the C++ side —
# a change here is a breaking protocol change.
EXPECTED_HEADER_SIZE = 9
EXPECTED_CLICK_PAYLOAD_SIZE = 18


class TestWireFormatSizes:
    """Absolute size guarantees the C++ implementation must match."""

    def test_header_format_is_nine_bytes(self):
        assert struct.calcsize(protocol.MSG_HEADER_FORMAT) == EXPECTED_HEADER_SIZE

    def test_click_format_is_eighteen_bytes(self):
        assert struct.calcsize(protocol.MSG_CLICK_FORMAT) == EXPECTED_CLICK_PAYLOAD_SIZE

    def test_header_format_has_no_alignment_padding(self):
        """The '<' prefix must suppress padding; native order would pad to 12."""
        unpadded_size = struct.calcsize('<IBI')
        assert struct.calcsize(protocol.MSG_HEADER_FORMAT) == unpadded_size


class TestFrame:
    """Tests for the generic header-prepending function."""

    def test_frame_prepends_header_to_payload(self):
        payload = b'\x01\x02\x03\x04'

        message = protocol.frame(protocol.MsgType.CLICK, payload)

        assert message[EXPECTED_HEADER_SIZE:] == payload

    def test_frame_total_length_is_header_plus_payload(self):
        payload = b'\x01\x02\x03\x04'

        message = protocol.frame(protocol.MsgType.CLICK, payload)

        assert len(message) == EXPECTED_HEADER_SIZE + len(payload)

    def test_frame_records_payload_length_in_bytes_not_elements(self):
        """payload_len is a byte count — a classic off-by-encoding bug."""
        payload = b'\x00' * 18

        message = protocol.frame(protocol.MsgType.CLICK, payload)
        _, payload_len = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        assert payload_len == 18

    def test_frame_handles_empty_payload(self):
        message = protocol.frame(protocol.MsgType.READY, b'')

        assert len(message) == EXPECTED_HEADER_SIZE


class TestParseHeader:
    """Tests for header parsing and magic-number validation."""

    def test_parse_header_returns_message_type_and_payload_length(self):
        message = protocol.frame(protocol.MsgType.CLICK, b'\x00' * 18)

        msg_type, payload_len = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        assert (msg_type, payload_len) == (protocol.MsgType.CLICK, 18)

    def test_parse_header_raises_on_bad_magic(self):
        corrupt_header = struct.pack(protocol.MSG_HEADER_FORMAT,
                                     0xDEADBEEF, protocol.MsgType.CLICK, 18)

        with pytest.raises(ValueError, match='bad magic'):
            protocol.parse_header(corrupt_header)

    def test_parse_header_raises_on_truncated_header(self):
        truncated = b'\x00' * (EXPECTED_HEADER_SIZE - 1)

        with pytest.raises(struct.error):
            protocol.parse_header(truncated)


class TestHelloRoundTrip:
    """Tests that decode_hello inverts encode_hello."""

    def test_decode_hello_recovers_original_hello(self):
        original = protocol.Hello(count=1000, checksum=0xDEADBEEF)

        message = protocol.encode_hello(original)
        decoded = protocol.decode_hello(message[EXPECTED_HEADER_SIZE:])

        assert decoded == original

    def test_encode_hello_sets_correct_message_type(self):
        hello = protocol.Hello(100, 42)

        message = protocol.encode_hello(hello)
        msg_type, _ = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        assert msg_type == protocol.MsgType.HELLO

    def test_encode_hello_produces_correct_payload_size(self):
        hello = protocol.Hello(50000, 0xCAFEBABE)

        message = protocol.encode_hello(hello)
        _, payload_len = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        expected_payload_len = struct.calcsize(protocol.MSG_HELLO_FORMAT)
        assert payload_len == expected_payload_len

    def test_hello_round_trip_zero_count(self):
        original = protocol.Hello(0, 0)

        decoded = protocol.decode_hello(
            protocol.encode_hello(original)[EXPECTED_HEADER_SIZE:])

        assert decoded == original

    def test_hello_round_trip_max_values(self):
        max_uint32 = 2**32 - 1
        original = protocol.Hello(max_uint32, max_uint32)

        decoded = protocol.decode_hello(
            protocol.encode_hello(original)[EXPECTED_HEADER_SIZE:])

        assert decoded.count == max_uint32
        assert decoded.checksum == max_uint32


class TestHelloBoundaryValues:
    """Boundary values for Hello encoding."""

    def test_hello_rejects_negative_count(self):
        hello = protocol.Hello(-1, 0)

        with pytest.raises(ValueError, match='invalid point count'):
            protocol.encode_hello(hello)


class TestReadyRoundTrip:
    """Tests that decode_ready inverts encode_ready."""

    def test_decode_ready_recovers_original_ready(self):
        original = protocol.Ready(ok=1)

        message = protocol.encode_ready(original)
        decoded = protocol.decode_ready(message[EXPECTED_HEADER_SIZE:])

        assert decoded == original

    def test_encode_ready_sets_correct_message_type(self):
        ready = protocol.Ready(ok=1)

        message = protocol.encode_ready(ready)
        msg_type, _ = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        assert msg_type == protocol.MsgType.READY

    def test_encode_ready_produces_correct_payload_size(self):
        ready = protocol.Ready(0)

        message = protocol.encode_ready(ready)
        _, payload_len = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        expected_payload_len = struct.calcsize(protocol.MSG_READY_FORMAT)
        assert payload_len == expected_payload_len

    def test_ready_round_trip_true(self):
        original = protocol.Ready(1)

        decoded = protocol.decode_ready(
            protocol.encode_ready(original)[EXPECTED_HEADER_SIZE:])

        assert decoded.ok == 1

    def test_ready_round_trip_false(self):
        original = protocol.Ready(0)

        decoded = protocol.decode_ready(
            protocol.encode_ready(original)[EXPECTED_HEADER_SIZE:])

        assert decoded.ok == 0


class TestReadyBoundaryValues:
    """Boundary values for Ready encoding."""

    def test_ready_rejects_invalid_ok_flag(self):
        ready = protocol.Ready(2)

        with pytest.raises(ValueError, match='invalid ok flag'):
            protocol.encode_ready(ready)


class TestClickRoundTrip:
    """Tests that decode_click inverts encode_click."""

    def test_decode_click_recovers_original_click(self):
        original = protocol.Click(point_index=42, x=1.0, y=2.0, z=3.0,
                                  class_id=protocol.CLASS_ID['STEM'],
                                  positive_flag=1)

        message = protocol.encode_click(original)
        decoded = protocol.decode_click(message[EXPECTED_HEADER_SIZE:])

        assert decoded == original

    def test_decode_click_preserves_negative_flag(self):
        """Negative clicks drive refinement — this field must survive."""
        original = protocol.Click(point_index=7, x=0.0, y=0.0, z=0.0,
                                  class_id=protocol.CLASS_ID['FOLIAGE'],
                                  positive_flag=0)

        decoded = protocol.decode_click(
            protocol.encode_click(original)[EXPECTED_HEADER_SIZE:])

        assert decoded.positive_flag == 0

    def test_encode_click_produces_correct_total_message_size(self):
        click = protocol.Click(0, 0.0, 0.0, 0.0, 0, 0)

        message = protocol.encode_click(click)

        assert len(message) == EXPECTED_HEADER_SIZE + EXPECTED_CLICK_PAYLOAD_SIZE

    def test_encode_click_sets_correct_message_type(self):
        click = protocol.Click(0, 0.0, 0.0, 0.0, 0, 0)

        message = protocol.encode_click(click)
        msg_type, _ = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        assert msg_type == protocol.MsgType.CLICK


class TestClickBoundaryValues:
    """Boundary values that would silently corrupt if field widths are wrong."""

    def test_click_accepts_maximum_point_index(self):
        """uint32 max — catches a field mistyped as uint16."""
        max_uint32 = 2**32 - 1
        original = protocol.Click(max_uint32, 0.0, 0.0, 0.0, 0, 1)

        decoded = protocol.decode_click(
            protocol.encode_click(original)[EXPECTED_HEADER_SIZE:])

        assert decoded.point_index == max_uint32

    def test_click_rejects_out_of_range_point_index(self):
        too_large = 2**32
        click = protocol.Click(too_large, 0.0, 0.0, 0.0, 0, 1)

        with pytest.raises(struct.error):
            protocol.encode_click(click)

    def test_click_preserves_negative_coordinates(self):
        original = protocol.Click(1, -12.5, -0.25, -100.0, 0, 1)

        decoded = protocol.decode_click(
            protocol.encode_click(original)[EXPECTED_HEADER_SIZE:])

        assert (decoded.x, decoded.y, decoded.z) == (-12.5, -0.25, -100.0)

    @pytest.mark.parametrize('class_name', ['STEM', 'FOLIAGE', 'GROUND',
                                            'UNDERGROWTH'])
    def test_click_round_trips_every_class_id(self, class_name):
        original = protocol.Click(1, 0.0, 0.0, 0.0,
                                  protocol.CLASS_ID[class_name], 1)

        decoded = protocol.decode_click(
            protocol.encode_click(original)[EXPECTED_HEADER_SIZE:])

        assert decoded.class_id == protocol.CLASS_ID[class_name]


class TestLabelsRoundTrip:
    """Tests that decode_labels inverts encode_labels."""

    def test_decode_labels_recovers_original_labels(self):
        original = protocol.Labels([1, 42, 7],
                                   [protocol.CLASS_ID['STEM'],
                                    protocol.CLASS_ID['FOLIAGE'],
                                    protocol.CLASS_ID['GROUND']])

        message = protocol.encode_labels(original)
        decoded = protocol.decode_labels(message[EXPECTED_HEADER_SIZE:])

        assert decoded.point_indices == original.point_indices
        assert decoded.class_ids == original.class_ids

    def test_encode_labels_sets_correct_message_type(self):
        labels = protocol.Labels([1, 2], [0, 1])

        message = protocol.encode_labels(labels)
        msg_type, _ = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        assert msg_type == protocol.MsgType.LABELS

    def test_encode_labels_records_correct_payload_length(self):
        labels = protocol.Labels([1, 2, 3], [0, 1, 2])

        message = protocol.encode_labels(labels)
        _, payload_len = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        expected_payload_len = 4 + 5 * 3  # count (4 bytes) + 3 pairs of (IB)
        assert payload_len == expected_payload_len

    def test_labels_round_trip_single_point(self):
        original = protocol.Labels([99], [protocol.CLASS_ID['UNDERGROWTH']])

        decoded = protocol.decode_labels(
            protocol.encode_labels(original)[EXPECTED_HEADER_SIZE:])

        assert decoded == original

    def test_labels_round_trip_empty(self):
        original = protocol.Labels([], [])

        decoded = protocol.decode_labels(
            protocol.encode_labels(original)[EXPECTED_HEADER_SIZE:])

        assert decoded.point_indices == []
        assert decoded.class_ids == []


class TestLabelsBoundaryValues:
    """Boundary values for Labels encoding."""

    def test_labels_accepts_maximum_point_index(self):
        """uint32 max — catches a field mistyped as uint16."""
        max_uint32 = 2**32 - 1
        original = protocol.Labels([max_uint32], [0])

        decoded = protocol.decode_labels(
            protocol.encode_labels(original)[EXPECTED_HEADER_SIZE:])

        assert decoded.point_indices[0] == max_uint32

    def test_labels_rejects_mismatched_lengths(self):
        labels = protocol.Labels([1, 2], [0])

        with pytest.raises(ValueError, match='mismatch length'):
            protocol.encode_labels(labels)

    def test_labels_rejects_invalid_class_id(self):
        labels = protocol.Labels([1], [999])

        with pytest.raises(ValueError, match='invalid class_id'):
            protocol.encode_labels(labels)

    @pytest.mark.parametrize('class_name', ['STEM', 'FOLIAGE', 'GROUND',
                                            'UNDERGROWTH'])
    def test_labels_round_trips_every_class_id(self, class_name):
        original = protocol.Labels([1, 2, 3, 4],
                                   [protocol.CLASS_ID[class_name]] * 4)

        decoded = protocol.decode_labels(
            protocol.encode_labels(original)[EXPECTED_HEADER_SIZE:])

        assert all(cid == protocol.CLASS_ID[class_name] for cid in decoded.class_ids)


class TestFullLabelsRoundTrip:
    """Tests that decode_full_labels inverts encode_full_labels."""

    def test_decode_full_labels_recovers_original_array(self):
        original = np.array([0, 1, 2, 3, 0, 1, 2], dtype=np.uint8)

        message = protocol.encode_full_labels(original)
        decoded = protocol.decode_full_labels(message[EXPECTED_HEADER_SIZE:])

        np.testing.assert_array_equal(decoded, original)

    def test_encode_full_labels_sets_correct_message_type(self):
        labels = np.array([0, 1, 2], dtype=np.uint8)

        message = protocol.encode_full_labels(labels)
        msg_type, _ = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        assert msg_type == protocol.MsgType.FULL_LABELS

    def test_encode_full_labels_records_correct_payload_length(self):
        labels = np.array([1, 2, 3, 0], dtype=np.uint8)

        message = protocol.encode_full_labels(labels)
        _, payload_len = protocol.parse_header(message[:EXPECTED_HEADER_SIZE])

        expected_payload_len = 4 + len(labels)  # count (4 bytes) + array bytes
        assert payload_len == expected_payload_len

    def test_full_labels_round_trip_single_point(self):
        original = np.array([protocol.CLASS_ID['UNDERGROWTH']], dtype=np.uint8)

        message = protocol.encode_full_labels(original)
        decoded = protocol.decode_full_labels(message[EXPECTED_HEADER_SIZE:])

        np.testing.assert_array_equal(decoded, original)

    def test_full_labels_round_trip_empty(self):
        original = np.array([], dtype=np.uint8)

        message = protocol.encode_full_labels(original)
        decoded = protocol.decode_full_labels(message[EXPECTED_HEADER_SIZE:])

        assert len(decoded) == 0

    def test_full_labels_preserves_dtype(self):
        """Decoded array must be uint8."""
        original = np.array([0, 1, 2, 3], dtype=np.uint8)

        message = protocol.encode_full_labels(original)
        decoded = protocol.decode_full_labels(message[EXPECTED_HEADER_SIZE:])

        assert decoded.dtype == np.uint8


class TestFullLabelsBoundaryValues:
    """Boundary values for full labels encoding."""

    def test_full_labels_accepts_all_class_ids(self):
        """Dense label array must accept all valid class IDs."""
        class_ids = list(protocol.CLASS_ID.values())
        original = np.array(class_ids, dtype=np.uint8)

        message = protocol.encode_full_labels(original)
        decoded = protocol.decode_full_labels(message[EXPECTED_HEADER_SIZE:])

        np.testing.assert_array_equal(decoded, original)

    def test_full_labels_rejects_invalid_class_id(self):
        """Invalid class ID (e.g., 254, which is not UNLABELLED) should raise ValueError."""
        labels = np.array([0, 1, 254, 2], dtype=np.uint8)

        with pytest.raises(ValueError, match='invalid class_id'):
            protocol.encode_full_labels(labels)

    def test_full_labels_handles_large_arrays(self):
        """Encode/decode large point clouds."""
        original = np.random.randint(0, 4, size=10000, dtype=np.uint8)

        message = protocol.encode_full_labels(original)
        decoded = protocol.decode_full_labels(message[EXPECTED_HEADER_SIZE:])

        np.testing.assert_array_equal(decoded, original)

    def test_full_labels_converts_to_uint8(self):
        """Input is coerced to uint8 if possible."""
        original_list = [0, 1, 2, 3]
        original_arr = np.array(original_list, dtype=np.uint8)

        message = protocol.encode_full_labels(original_list)
        decoded = protocol.decode_full_labels(message[EXPECTED_HEADER_SIZE:])

        np.testing.assert_array_equal(decoded, original_arr)