from mcp_gdbserver.svd import SVDDevice


MINIMAL_SVD = """\
<?xml version="1.0" encoding="utf-8"?>
<device>
  <name>STM32_TEST</name>
  <peripherals>
    <peripheral>
      <name>I2C1</name>
      <baseAddress>0x40005400</baseAddress>
      <description>I2C controller</description>
      <registers>
        <register>
          <name>CR1</name>
          <description>Control register 1</description>
          <addressOffset>0x00</addressOffset>
          <size>32</size>
          <resetValue>0x00000000</resetValue>
          <fields>
            <field>
              <name>PE</name>
              <description>Peripheral enable</description>
              <bitOffset>0</bitOffset>
              <bitWidth>1</bitWidth>
            </field>
            <field>
              <name>DNF</name>
              <bitRange>[11:8]</bitRange>
            </field>
          </fields>
        </register>
      </registers>
    </peripheral>
    <peripheral derivedFrom="I2C1">
      <name>I2C2</name>
      <baseAddress>0x40005800</baseAddress>
    </peripheral>
  </peripherals>
</device>
"""


def test_svd_parses_peripherals_registers_and_fields(tmp_path) -> None:
    svd_path = tmp_path / "minimal.svd"
    svd_path.write_text(MINIMAL_SVD, encoding="utf-8")

    device = SVDDevice.from_file(svd_path)

    assert device.name == "STM32_TEST"
    assert len(device.peripherals) == 2

    i2c1 = device.peripheral_by_name("i2c1")
    assert i2c1 is not None
    assert i2c1.base_address == 0x40005400

    cr1 = i2c1.register_by_name("cr1")
    assert cr1 is not None
    assert cr1.absolute_address(i2c1) == 0x40005400
    assert cr1.fields[0].decode(0x0101) == 1
    assert cr1.fields[1].decode(0x0A00) == 0xA


def test_svd_supports_peripheral_derived_from(tmp_path) -> None:
    svd_path = tmp_path / "minimal.svd"
    svd_path.write_text(MINIMAL_SVD, encoding="utf-8")

    device = SVDDevice.from_file(svd_path)
    i2c2 = device.peripheral_by_name("I2C2")

    assert i2c2 is not None
    assert i2c2.base_address == 0x40005800
    assert i2c2.register_by_name("CR1") is not None
