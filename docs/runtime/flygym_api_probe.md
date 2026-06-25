# FlyGym API Probe

- JSON report: `outputs/smoke/body/flygym_api.json`
- Last generated artifact path: `outputs/smoke/body/flygym_api.json`
- Schema version: `1`
- FlyGym: `2.0.2`
- MuJoCo: `3.6.0`
- Locomotion controller status: `demo_controllers_available`
- Controller imports: `flygym_demo.complex_terrain.cpg_controller.CPGController, flygym_demo.complex_terrain.rule_based_controller.RuleBasedController, flygym_demo.complex_terrain.hybrid_controller.HybridController, flygym_demo.complex_terrain.turning_controller.HybridTurningController`
- Actuator type: `position`
- Actuator count: `126`
- Proboscis control: supported
- Proboscis DOFs: `c_head-c_rostrum-pitch, c_head-c_rostrum-roll, c_head-c_rostrum-yaw, c_rostrum-c_haustellum-pitch, c_rostrum-c_haustellum-roll, c_rostrum-c_haustellum-yaw`
- Antenna control: supported
- Antenna DOFs: `c_head-l_pedicel-pitch, c_head-l_pedicel-roll, c_head-l_pedicel-yaw, l_pedicel-l_funiculus-pitch, l_pedicel-l_funiculus-roll, l_pedicel-l_funiculus-yaw, l_funiculus-l_arista-pitch, l_funiculus-l_arista-roll, l_funiculus-l_arista-yaw, c_head-r_pedicel-pitch, c_head-r_pedicel-roll, c_head-r_pedicel-yaw, r_pedicel-r_funiculus-pitch, r_pedicel-r_funiculus-roll, r_pedicel-r_funiculus-yaw, r_funiculus-r_arista-pitch, r_funiculus-r_arista-roll, r_funiculus-r_arista-yaw`
- Front-leg face grooming: supported
- Front-leg grooming DOFs: `c_thorax-lf_coxa-pitch, c_thorax-lf_coxa-roll, c_thorax-lf_coxa-yaw, lf_coxa-lf_trochanterfemur-pitch, lf_coxa-lf_trochanterfemur-roll, lf_trochanterfemur-lf_tibia-pitch, lf_tibia-lf_tarsus1-pitch, lf_tarsus1-lf_tarsus2-pitch, lf_tarsus2-lf_tarsus3-pitch, lf_tarsus3-lf_tarsus4-pitch, lf_tarsus4-lf_tarsus5-pitch, c_thorax-rf_coxa-pitch, c_thorax-rf_coxa-roll, c_thorax-rf_coxa-yaw, rf_coxa-rf_trochanterfemur-pitch, rf_coxa-rf_trochanterfemur-roll, rf_trochanterfemur-rf_tibia-pitch, rf_tibia-rf_tarsus1-pitch, rf_tarsus1-rf_tarsus2-pitch, rf_tarsus2-rf_tarsus3-pitch, rf_tarsus3-rf_tarsus4-pitch, rf_tarsus4-rf_tarsus5-pitch`
- Site positions: supported

The installed FlyGym 2 surface selected for body work is the compositional
`flygym.Simulation` API with position actuators ordered by the installed
`Skeleton(ALL_BIOLOGICAL, PITCH_ROLL_YAW)` joint DOF order. The report
does not claim a core `flygym` high-level behavior controller when only
`flygym_demo.complex_terrain` controller examples are available.
