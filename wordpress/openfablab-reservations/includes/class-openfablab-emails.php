<?php
if (!defined('ABSPATH')) { exit; }

/** Plain-text substitution only: no executable template language or reservation writes. */
final class OpenFabLab_Emails {
    private const OPTION = 'openfablab_res_email_settings';
    private const NONCE = 'openfablab_res_email_templates';

    public static function defaults() {
        $details = "Date et heure : {{date}} à {{time}}\n{{slot_details}}\nDurée : {{duration_minutes}} minutes\nParticipant : {{participant_name}}\nIdentifiant : {{public_id_or_not_provided}}\nÂge minimum : {{age_rule}}";
        $cancel = "Je ne pourrai finalement pas venir :\n{{cancel_url}}";
        return [
            'confirmation'=>['label'=>'Confirmation de réservation', 'subject'=>'Réservation confirmée · {{animation_title}}',
                'body'=>"Bonjour {{first_name}} {{last_name}},\n\nRéservation confirmée : {{animation_title}}\n$details\n\n$cancel\n\n{{signature}}"],
            'waitlist'=>['label'=>'Inscription sur liste d’attente', 'subject'=>'Liste d’attente enregistrée · {{animation_title}}',
                'body'=>"Bonjour {{first_name}} {{last_name}},\n\nListe d’attente enregistrée : {{animation_title}}\nVous n’avez pas encore de place confirmée.\n$details\n\n$cancel\n\n{{signature}}"],
            'offer'=>['label'=>'Une place est disponible', 'subject'=>'Une place vient de se libérer · {{animation_title}}',
                'body'=>"Bonjour {{first_name}} {{last_name}},\n\nUne place vient de se libérer pour {{animation_title}}.\nDate et heure : {{date}} à {{time}}\n{{slot_details}}\nAcceptez ou refusez avant {{offer_deadline}} :\n{{offer_url}}\n\n{{signature}}"],
            'reminder_one'=>['label'=>'Premier rappel', 'subject'=>'Rappel · {{animation_title}}',
                'body'=>"Bonjour {{first_name}} {{last_name}},\n\nRappel : {{animation_title}}\nDate et heure : {{date}} à {{time}}\n{{slot_details}}\nSi vous ne pouvez pas venir, annulez pour libérer la place.\n$cancel\n\n{{signature}}"],
            'reminder_two'=>['label'=>'Deuxième rappel', 'subject'=>'Rappel · {{animation_title}}',
                'body'=>"Bonjour {{first_name}} {{last_name}},\n\nRappel : {{animation_title}}\nDate et heure : {{date}} à {{time}}\n{{slot_details}}\nSi vous ne pouvez pas venir, annulez pour libérer la place.\n$cancel\n\n{{signature}}"],
            'cancellation'=>['label'=>'Confirmation d’annulation', 'subject'=>'Réservation annulée · {{animation_title}}',
                'body'=>"Bonjour {{first_name}} {{last_name}},\n\nVotre réservation a bien été annulée.\n\nAnimation : {{animation_title}}\nDate et heure : {{date}} à {{time}}\n{{slot_details}}\nParticipant : {{participant_name}}\n\nMerci d’avoir prévenu suffisamment tôt afin de permettre à une autre personne de profiter de la place libérée.\n\n{{signature}}"],
        ];
    }

    public static function variables($kind) {
        $keys=['first_name','last_name','participant_name','public_id','public_id_or_not_provided',
            'animation_title','date','time','end_time','duration_minutes','slot','slot_details',
            'minimum_age','accompaniment_age','age_rule','signature','structure_name','site_url','privacy_url'];
        if (in_array($kind,['confirmation','waitlist','reminder_one','reminder_two'],true)) { $keys[]='cancel_url'; }
        if ($kind==='offer') { $keys[]='offer_url'; $keys[]='offer_deadline'; }
        return $keys;
    }

    private static function text($value) {
        if (!is_string($value)) { throw new InvalidArgumentException('Le modèle doit être du texte.'); }
        if (preg_match('//u',$value)!==1) { throw new InvalidArgumentException('Utilisez un texte UTF-8 valide.'); }
        return trim(str_replace(["\r\n","\r","\0"],["\n","\n",''],strip_tags($value)));
    }

    public static function validate($kind, $subject, $body) {
        if (!isset(self::defaults()[$kind])) { throw new InvalidArgumentException('Modèle inconnu.'); }
        $subject=self::text($subject); $body=self::text($body);
        if ($subject==='' || $body==='' || strlen($subject)>300 || strlen($body)>20000 || preg_match('/[\r\n\x00-\x1f]/',$subject)) {
            throw new InvalidArgumentException('Sujet et corps obligatoires ; sujet sur une seule ligne (300 caractères maximum), corps limité à 20 000 caractères.');
        }
        foreach ([$subject,$body] as $value) {
            preg_match_all('/\{\{([^{}]*)\}\}/u',$value,$matches);
            foreach ($matches[1] as $key) {
                if (!in_array($key,self::variables($kind),true)) { throw new InvalidArgumentException('Variable inconnue ou indisponible : {{'.$key.'}}.'); }
            }
            if (preg_match('/\{\{|\}\}/',preg_replace('/\{\{[a-z_]+\}\}/u','',$value))) {
                throw new InvalidArgumentException('Variable mal formée : utilisez exactement {{nom_variable}}.');
            }
        }
        // A usable cancellation/offer path must survive customisation.
        $required=$kind==='offer'?'offer_url':(in_array($kind,['confirmation','waitlist','reminder_one','reminder_two'],true)?'cancel_url':null);
        if ($required && !str_contains($body,'{{'.$required.'}}')) { throw new InvalidArgumentException('Le corps doit conserver {{'.$required.'}} pour rendre le lien utilisable.'); }
        return ['subject'=>$subject,'body'=>$body];
    }

    private static function settings() {
        $value=get_option(self::OPTION,[]);
        if (!is_array($value)) { return []; }
        if (isset($value['templates']) && !is_array($value['templates'])) { $value['templates']=[]; }
        return $value;
    }

    public static function template($kind) {
        $defaults=self::defaults();
        if (!isset($defaults[$kind])) { throw new InvalidArgumentException('Modèle inconnu.'); }
        $custom=self::settings()['templates'][$kind]??null;
        if (is_array($custom)) {
            try { return self::validate($kind,$custom['subject']??'',$custom['body']??''); }
            catch (InvalidArgumentException $error) { /* Corrupt/empty options never produce empty mail. */ }
        }
        return ['subject'=>$defaults[$kind]['subject'],'body'=>$defaults[$kind]['body']];
    }

    public static function signature() {
        $settings=self::settings();
        if (isset($settings['signature']) && is_string($settings['signature'])) { return self::text($settings['signature']); }
        return self::text((string)get_option('openfablab_res_from_name',get_bloginfo('name')))."\n"
            .sanitize_email(get_option('openfablab_res_reply_to',get_option('admin_email')))."\n".home_url('/');
    }

    public static function context($row, $animation, $extra=[]) {
        $animation=OpenFabLab_Slots::context($animation,$row['slot_uuid']??null);
        $zone=new DateTimeZone($animation['timezone']);
        $start=(new DateTimeImmutable($animation['starts_at'],new DateTimeZone('UTC')))->setTimezone($zone);
        $end=(new DateTimeImmutable($animation['ends_at'],new DateTimeZone('UTC')))->setTimezone($zone);
        $age=(int)($animation['minimum_age']??0); $accompaniment=(int)($animation['accompaniment_under_age']??0);
        $slot=OpenFabLab_Slots::enabled($animation)?$start->format('H:i').'–'.$end->format('H:i'):'';
        $id=trim((string)($row['public_id']??''));
        return [
            'first_name'=>(string)($row['first_name']??''),'last_name'=>(string)($row['last_name']??''),
            'participant_name'=>trim(($row['first_name']??'').' '.($row['last_name']??'')),
            'public_id'=>$id?:'non renseigné','public_id_or_not_provided'=>$id?:'non renseigné',
            'animation_title'=>$animation['title'],'date'=>$start->format('d/m/Y'),'time'=>$start->format('H:i'),
            'end_time'=>$end->format('H:i'),'duration_minutes'=>(string)max(0,(int)(($end->getTimestamp()-$start->getTimestamp())/60)),
            'slot'=>$slot,'slot_details'=>$slot?'Créneau : '.$slot:'','minimum_age'=>(string)$age,
            'accompaniment_age'=>(string)$accompaniment,'age_rule'=>$age.' ans'.($accompaniment>0?' (et accompagnement requis avant '.$accompaniment.' ans)':''),
            'signature'=>self::signature(),'structure_name'=>get_option('openfablab_res_from_name',get_bloginfo('name')),
            'site_url'=>home_url('/'),'privacy_url'=>get_option('openfablab_res_privacy_url',''),
            'cancel_url'=>(string)($extra['cancel_url']??''),'offer_url'=>(string)($extra['offer_url']??''),
            'offer_deadline'=>(string)($extra['offer_deadline']??''),
        ];
    }

    public static function compose($kind, $row, $animation, $extra=[], $draft=null) {
        $template=$draft===null?self::template($kind):self::validate($kind,$draft['subject']??'',$draft['body']??'');
        $values=self::context($row,$animation,$extra); $replace=[];
        foreach (self::variables($kind) as $key) { $replace['{{'.$key.'}}']=self::text((string)($values[$key]??'')); }
        // Remove an optional slot line altogether in whole-animation mode.
        if (!$values['slot_details']) { $template['body']=preg_replace('/^[ \t]*\{\{slot_details\}\}[ \t]*\n?/m','',$template['body']); }
        $subject=strtr($template['subject'],$replace); $body=strtr($template['body'],$replace);
        $subject=trim(preg_replace('/[\r\n\x00-\x1f]+/',' ',strip_tags($subject)));
        return ['subject'=>$subject?:self::defaults()[$kind]['label'],'body'=>$body?:self::defaults()[$kind]['label']];
    }

    public static function deliver($to, $subject, $body, $environment, $test_message=false) {
        $to=sanitize_email($to); if (!$to || !is_email($to)) { return false; }
        $name=sanitize_text_field(get_option('openfablab_res_from_name',get_bloginfo('name')));
        $name=preg_replace('/[\r\n\x00-\x1f<>]+/',' ',$name);
        $from=sanitize_email(get_option('openfablab_res_from_email',get_option('admin_email')));
        $reply=sanitize_email(get_option('openfablab_res_reply_to',get_option('admin_email')));
        $prefix=$environment==='test'?sanitize_text_field(get_option('openfablab_res_test_prefix','[TEST OpenFabLab]')):'';
        $subject=preg_replace('/[\r\n\x00-\x1f]+/',' ',($test_message?'[TEST modèle OpenFabLab] ':'').($prefix?trim($prefix).' ':'').$subject);
        $headers=['Content-Type: text/plain; charset=UTF-8'];
        if ($from) { $headers[]="From: $name <$from>"; }
        if ($reply) { $headers[]="Reply-To: $reply"; }
        try { return (bool)wp_mail($to,$subject,$body,$headers); }
        catch (Throwable $error) { return false; } // Never expose private mail/filter errors.
    }

    public static function sample($slots=false) {
        $row=['first_name'=>'Camille','last_name'=>'EXEMPLE','public_id'=>'OFL-EXEMPLE','email'=>'participant@example.invalid',
            'environment'=>'test','slot_uuid'=>$slots?'20000000-0000-4000-8000-000000000001':null];
        $animation=['title'=>'Découverte — exemple fictif','timezone'=>'Europe/Paris','starts_at'=>'2099-10-08 08:00:00',
            'ends_at'=>'2099-10-08 10:00:00','minimum_age'=>10,'accompaniment_under_age'=>15,'booking_mode'=>$slots?'slots':'whole'];
        if ($slots) { $animation['slots_json']=wp_json_encode([['slot_uuid'=>$row['slot_uuid'],'starts_at'=>'2099-10-08 08:30:00',
            'ends_at'=>'2099-10-08 08:50:00','capacity'=>1]]); }
        return [$row,$animation,['cancel_url'=>'https://example.invalid/annulation-exemple','offer_url'=>'https://example.invalid/offre-exemple',
            'offer_deadline'=>'07/10/2099 à 18:00']];
    }

    public static function handle_request($request) {
        if (!is_user_logged_in() || !current_user_can('manage_options') || ($_SERVER['REQUEST_METHOD']??'')!=='POST'
            || !is_string($request['_wpnonce']??null)
            || !wp_verify_nonce($request['_wpnonce'],self::NONCE)) { return ['error'=>'Accès ou confirmation de sécurité refusé.']; }
        try {
            $action=$request['openfablab_email_action']??''; $settings=self::settings();
            if ($action==='signature') {
                $signature=self::text($request['signature']??'');
                if (strlen($signature)>10000) { throw new InvalidArgumentException('Signature limitée à 10 000 caractères.'); }
                $settings['signature']=$signature;
            } else {
                $kind=$request['email_model']??'';
                if (!is_string($kind) || !isset(self::defaults()[$kind])) { throw new InvalidArgumentException('Modèle inconnu.'); }
                if ($action==='reset') {
                    if (($request['reset_confirm']??'')!=='yes') { throw new InvalidArgumentException('Confirmez le retour au modèle générique avant de remplacer votre texte.'); }
                    unset($settings['templates'][$kind]);
                } elseif (in_array($action,['save','preview','send_test'],true)) {
                    $template=self::validate($kind,$request['subject']??'',$request['body']??'');
                    if ($action==='save') { $settings['templates'][$kind]=$template; }
                    else {
                        [$row,$animation,$extra]=self::sample(($request['sample_mode']??'whole')==='slots');
                        $mail=self::compose($kind,$row,$animation,$extra,$template);
                        if ($action==='preview') { return ['preview'=>$mail,'label'=>self::defaults()[$kind]['label'],'kind'=>$kind,'draft'=>$template]; }
                        $to=sanitize_email($request['test_recipient']??'');
                        if (!$to || !is_email($to)) { throw new InvalidArgumentException('Saisissez une adresse de test valide.'); }
                        $key='openfablab_res_email_test_'.get_current_user_id();
                        if (get_transient($key)) { throw new InvalidArgumentException('Attendez une minute avant un nouvel envoi de test.'); }
                        set_transient($key,1,60);
                        if (!self::deliver($to,$mail['subject'],$mail['body'],'test',true)) { throw new InvalidArgumentException('Envoi de test impossible ; vérifiez la configuration de messagerie WordPress.'); }
                        return ['success'=>'E-mail de test envoyé avec des données fictives ; la réception reste à vérifier.','kind'=>$kind,'draft'=>$template];
                    }
                } else { throw new InvalidArgumentException('Action inconnue.'); }
            }
            // Single non-autoloaded option: no schema migration or sync event.
            if ($settings!==self::settings() && !update_option(self::OPTION,$settings,false)) { throw new InvalidArgumentException('Enregistrement impossible.'); }
            return ['success'=>$action==='reset'?'Modèle générique restauré.':'Réglages des e-mails enregistrés.'];
        } catch (InvalidArgumentException $error) {
            $result=['error'=>$error->getMessage()];
            // Preserve edited text after an error/preview instead of silently discarding it.
            $kind=$request['email_model']??null;
            if (is_string($kind) && isset(self::defaults()[$kind]) && is_string($request['subject']??null) && is_string($request['body']??null)
                && strlen($request['subject'])<=1200 && strlen($request['body'])<=20000) {
                $result['kind']=$kind; $result['draft']=['subject'=>$request['subject'],'body'=>$request['body']];
            }
            return $result;
        }
    }

    public static function render($result=null) {
        if (!is_user_logged_in() || !current_user_can('manage_options')) { return; }
        echo '<section id="openfablab-email-models"><h2>Modèles d’e-mails</h2><p>Texte brut UTF-8, propre à cette installation. Les champs sont remplacés sans exécuter de code. Les liens d’annulation et d’offre doivent rester dans les modèles concernés.</p>';
        if ($result) {
            if (isset($result['error']) || isset($result['success'])) { echo '<div class="notice '.(isset($result['error'])?'notice-error':'notice-success').'"><p>'.esc_html($result['error']??$result['success']).'</p></div>'; }
            if (isset($result['preview'])) { echo '<h3>Prévisualisation fictive — '.esc_html($result['label']).'</h3><p><strong>Sujet :</strong> '.esc_html($result['preview']['subject']).'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-width:60rem">'.esc_html($result['preview']['body']).'</pre><p>Aucun envoi ni enregistrement pendant cette prévisualisation.</p>'; }
        }
        echo '<form method="post">'; wp_nonce_field(self::NONCE);
        echo '<h3><label for="openfablab-email-signature">Signature / coordonnées communes</label></h3><p>Réutilisée avec {{signature}}. Sans personnalisation, reprend votre nom expéditeur, votre adresse de réponse et votre site.</p><textarea id="openfablab-email-signature" name="signature" rows="7" class="large-text" maxlength="10000">'.esc_html(self::signature()).'</textarea><p><button class="button" name="openfablab_email_action" value="signature">Enregistrer la signature</button></p></form>';
        foreach (self::defaults() as $kind=>$default) {
            $active=($result['kind']??null)===$kind;
            $template=$active && isset($result['draft'])?$result['draft']:self::template($kind); $id='openfablab-email-'.$kind;
            echo '<details '.($active?'open ':'').'style="margin:1rem 0;padding:1rem;background:#fff;border:1px solid #ccd0d4"><summary><strong>'.esc_html($default['label']).'</strong></summary><form method="post">'; wp_nonce_field(self::NONCE);
            echo '<input type="hidden" name="email_model" value="'.esc_attr($kind).'">';
            echo '<p><label for="'.esc_attr($id.'-subject').'">Sujet</label><input required maxlength="300" class="large-text" id="'.esc_attr($id.'-subject').'" name="subject" value="'.esc_attr($template['subject']).'"></p>';
            echo '<p><label for="'.esc_attr($id.'-body').'">Corps du message</label><textarea required maxlength="20000" class="large-text" rows="13" id="'.esc_attr($id.'-body').'" name="body">'.esc_html($template['body']).'</textarea></p>';
            echo '<p style="overflow-wrap:anywhere">Variables : '.esc_html(implode(' · ',array_map(fn($key)=>'{{'.$key.'}}',self::variables($kind)))).'</p><p>{{slot_details}} ajoute « Créneau : début–fin » uniquement en mode créneaux. {{public_id_or_not_provided}} affiche « non renseigné » sans identifiant. {{age_rule}} inclut la règle d’accompagnement.</p>';
            echo '<p><label>Exemple fictif <select name="sample_mode"><option value="whole">Animation classique</option><option value="slots">Animation par créneaux</option></select></label></p>';
            echo '<p><button class="button button-primary" name="openfablab_email_action" value="save">Enregistrer ce modèle</button> <button class="button" name="openfablab_email_action" value="preview">Prévisualiser</button></p>';
            echo '<p><label>Adresse de test <input type="email" name="test_recipient" class="regular-text"></label> <button class="button" name="openfablab_email_action" value="send_test">Envoyer un e-mail de test</button></p><p>Les essais n’utilisent aucune réservation réelle. Les champs non enregistrés sont utilisés pour l’aperçu ou l’envoi uniquement ; la signature est celle enregistrée.</p>';
            echo '<p><label><input type="checkbox" name="reset_confirm" value="yes"> Je confirme le remplacement par le modèle générique</label> <button class="button" name="openfablab_email_action" value="reset" formnovalidate>Réinitialiser ce modèle</button></p></form></details>';
        }
        echo '</section>';
    }
}
