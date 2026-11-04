<?php
// Actual plugin classes, fictional WP hooks/options and signed transport only.
require __DIR__.'/test_v2141_public_resources.php';
$initial=$checks;
foreach (['resources','machines','equipment','rooms'] as $label) {
 $snapshot['resource_label']=$label;
 check(OpenFabLab_Public::valid_snapshot($snapshot),'predefined public label accepted '.$label);
 $options['openfablab_public_snapshot_production']=['data'=>$snapshot,'received_at'=>time()];
 check(OpenFabLab_Public::read('machines','production')->data['resource_label']===$label,'public endpoint passes exact label '.$label);
}
foreach (['<script>','Machine',false,1,['rooms']] as $label) {
 $bad=$snapshot;$bad['resource_label']=$label;
 check(!OpenFabLab_Public::valid_snapshot($bad),'unknown or non-string public label refused');
}
$snapshot['calendar'][1]['attendance_average']['method']='observed_same_weekday_hours_12m_v1';
$snapshot['calendar'][1]['attendance_average']['since']='2025-11-03';
$snapshot['calendar'][1]['attendance_average']['until']='2026-11-02';
check(OpenFabLab_Public::valid_snapshot($snapshot),'twelve-month aggregate accepted without protocol change');
$bad=$snapshot;$bad['calendar'][1]['attendance_average']['method']='unknown_method';
check(!OpenFabLab_Public::valid_snapshot($bad),'unknown average methodology refused');
unset($snapshot['resource_label']);$snapshot['calendar'][1]['attendance_average']['method']='observed_same_weekday_hours_26w_v1';
check(OpenFabLab_Public::valid_snapshot($snapshot),'old application projection remains compatible');
echo ($checks-$initial)." new 2.14.2 WordPress checks passed\n";
