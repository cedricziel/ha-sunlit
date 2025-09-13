# Battery SOC Event System

The Sunlit integration provides a comprehensive event system for battery State of Charge (SOC) monitoring. This enables sophisticated automations that react to battery state changes in real-time.

## Event Types

### 1. Threshold Events (`sunlit_soc_threshold`)

Fired when battery SOC crosses predefined thresholds.

**Event Data:**
```yaml
event_type: sunlit_soc_threshold
data:
  device_key: "battery_12345_system"  # Unique device identifier
  family_id: "family_67890"           # Solar system family ID
  threshold_name: "low"               # critical_low, low, high, critical_high
  threshold_value: 20                 # Threshold percentage
  current_soc: 18.5                   # Current SOC percentage
  previous_soc: 22.3                  # Previous SOC percentage
  direction: "below"                  # "above" or "below"
  timestamp: "2024-01-15T10:30:00Z"   # ISO timestamp
```

**Default Thresholds:**
- `critical_low`: 10%
- `low`: 20%
- `high`: 90%
- `critical_high`: 95%

### 2. Significant Change Events (`sunlit_soc_change`)

Fired when SOC changes by a significant amount (default: ±5%).

**Event Data:**
```yaml
event_type: sunlit_soc_change
data:
  device_key: "battery_12345_system"
  family_id: "family_67890"
  change_amount: 7.2                  # Absolute change in percentage
  change_threshold: 5                 # Configured change threshold
  current_soc: 42.8                   # Current SOC percentage
  baseline_soc: 50.0                  # SOC when last change event fired
  direction: "decrease"               # "increase" or "decrease"
  timestamp: "2024-01-15T10:30:00Z"
```

### 3. Limit Events (`sunlit_soc_limit`)

Fired when SOC reaches configured system limits (strategy, BMS, hardware).

**Event Data:**
```yaml
event_type: sunlit_soc_limit
data:
  device_key: "battery_12345_system"
  family_id: "family_67890"
  limit_type: "strategy_min"          # strategy_min/max, bms_min/max, hw_min/max
  limit_value: 15                     # Limit percentage
  current_soc: 15.2                   # Current SOC percentage
  tolerance: 1.0                      # Tolerance for limit detection
  timestamp: "2024-01-15T10:30:00Z"
```

## Device Keys

Events use structured device keys to identify different battery components:

- **System SOC**: `battery_{device_id}_system` - Overall battery system
- **Module SOC**: `battery_{device_id}_module{N}` - Individual battery modules (N = 1, 2, 3)

Example device keys:
- `battery_12345_system` - Main battery system SOC
- `battery_12345_module1` - First battery module (B215 expansion)
- `battery_12345_module2` - Second battery module
- `battery_12345_module3` - Third battery module

## Configuration

### Via Integration Options

1. Go to **Settings** → **Devices & Services**
2. Find the **Sunlit** integration
3. Click **Configure** (gear icon)
4. Adjust SOC event settings:

**Available Options:**
- **Enable SOC Events**: Turn event system on/off
- **Critical Low Threshold**: SOC % considered critically low (default: 10%)
- **Low Threshold**: SOC % considered low (default: 20%)
- **High Threshold**: SOC % considered high (default: 90%)
- **Critical High Threshold**: SOC % considered critically high (default: 95%)
- **Significant Change Threshold**: Minimum % change to trigger events (default: 5%)
- **Minimum Event Interval**: Rate limiting in seconds (default: 60s)

## Binary Sensors

In addition to events, the integration provides binary sensors for current battery states:

- `binary_sensor.{family_name}_battery_low` - True when SOC is low
- `binary_sensor.{family_name}_battery_critical_low` - True when SOC is critically low
- `binary_sensor.{family_name}_battery_high` - True when SOC is high
- `binary_sensor.{family_name}_battery_critical_high` - True when SOC is critically high

These sensors update with the device coordinator (every 30 seconds) and respect your configured thresholds.

## Rate Limiting

To prevent event spam, the system implements rate limiting:

- **Same threshold events**: Minimum interval between crossing the same threshold (default: 60 seconds)
- **Change events**: Only fire when cumulative change exceeds threshold since last event
- **Limit events**: Rate limited per limit type to prevent repeated alerts

## Example Automations

### Basic Low Battery Alert

```yaml
- alias: "Battery Low Alert"
  trigger:
    - platform: event
      event_type: sunlit_soc_threshold
      event_data:
        threshold_name: "low"
        direction: "below"
  action:
    - service: notify.mobile_app_phone
      data:
        message: "Battery low: {{ trigger.event.data.current_soc }}%"
```

### Energy Saving Mode

```yaml
- alias: "Critical Battery - Energy Saving"
  trigger:
    - platform: event
      event_type: sunlit_soc_threshold
      event_data:
        threshold_name: "critical_low"
        direction: "below"
  action:
    # Turn off non-essential devices
    - service: switch.turn_off
      target:
        area_id: "pool"
    - service: climate.set_temperature
      target:
        area_id: "house"
      data:
        temperature: 18  # Reduce heating
```

### Module-Specific Monitoring

```yaml
- alias: "Battery Module Alert"
  trigger:
    - platform: event
      event_type: sunlit_soc_threshold
  condition:
    - condition: template
      value_template: "{{ 'module' in trigger.event.data.device_key }}"
    - condition: template
      value_template: "{{ trigger.event.data.threshold_name == 'critical_low' }}"
  action:
    - service: notify.maintenance
      data:
        message: >
          Battery module issue: {{ trigger.event.data.device_key }}
          at {{ trigger.event.data.current_soc }}%
```

### Rapid Drain Detection

```yaml
- alias: "Rapid Battery Drain Alert"
  trigger:
    - platform: event
      event_type: sunlit_soc_change
  condition:
    - condition: template
      value_template: >
        {{ trigger.event.data.direction == 'decrease' and
           trigger.event.data.change_amount > 15 }}
  action:
    - service: notify.mobile_app_phone
      data:
        title: "Rapid Battery Drain!"
        message: >
          Battery dropped {{ trigger.event.data.change_amount }}%
          in short time. Check for high power usage.
```

## Advanced Use Cases

### Power Management System

Combine SOC events with other sensors to create intelligent power management:

```yaml
- alias: "Smart Power Management"
  trigger:
    - platform: event
      event_type: sunlit_soc_threshold
  action:
    - choose:
        # Critical low - emergency mode
        - conditions:
            - condition: template
              value_template: "{{ trigger.event.data.threshold_name == 'critical_low' }}"
          sequence:
            - service: scene.turn_on
              target:
                entity_id: scene.emergency_power_saving
        # Low battery - reduce usage
        - conditions:
            - condition: template
              value_template: "{{ trigger.event.data.threshold_name == 'low' }}"
          sequence:
            - service: climate.set_temperature
              target:
                area_id: "house"
              data:
                temperature: 19
        # High battery - resume normal operation
        - conditions:
            - condition: template
              value_template: "{{ trigger.event.data.threshold_name == 'high' and trigger.event.data.direction == 'above' }}"
          sequence:
            - service: scene.turn_on
              target:
                entity_id: scene.normal_operation
```

### Battery Health Monitoring

Track SOC patterns over time:

```yaml
- alias: "SOC Data Logger"
  trigger:
    - platform: event
      event_type: sunlit_soc_change
  action:
    - service: python_script.log_soc_data
      data:
        device: "{{ trigger.event.data.device_key }}"
        soc: "{{ trigger.event.data.current_soc }}"
        change: "{{ trigger.event.data.change_amount }}"
        direction: "{{ trigger.event.data.direction }}"
        timestamp: "{{ trigger.event.data.timestamp }}"
```

## Troubleshooting

### Events Not Firing

1. **Check Integration Status**: Ensure the Sunlit integration is loaded and coordinators are updating
2. **Verify Battery Data**: Check that `batterySoc` data is available in device sensors
3. **Options Configuration**: Verify SOC events are enabled in integration options
4. **Threshold Values**: Ensure thresholds are configured correctly for your system

### Too Many Events

1. **Adjust Thresholds**: Increase the significant change threshold (default 5%)
2. **Rate Limiting**: Increase minimum event interval (default 60 seconds)
3. **Filter Conditions**: Add conditions to automations to filter unwanted events

### Missing Module Events

1. **Check Module Detection**: Verify that battery modules are detected by the device coordinator
2. **Device Data**: Ensure `battery1Soc`, `battery2Soc`, `battery3Soc` fields are available
3. **Virtual Devices**: Check that virtual battery module devices are created

## Performance Considerations

- Events are dispatched during coordinator updates (every 30 seconds)
- Rate limiting prevents event spam but allows important changes through
- Binary sensors provide current state without waiting for threshold crossings
- Module events are only created for detected battery modules to avoid ghost devices

See `examples/soc_event_automations.yaml` for more automation examples.
