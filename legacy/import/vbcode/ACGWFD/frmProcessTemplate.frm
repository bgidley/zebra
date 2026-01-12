VERSION 5.00
Object = "{831FDD16-0C5C-11D2-A9FC-0000F8754DA1}#2.0#0"; "MSCOMCTL.OCX"
Begin VB.Form frmProcessTemplate 
   BorderStyle     =   3  'Fixed Dialog
   Caption         =   "Select Process Template"
   ClientHeight    =   3135
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   4650
   ControlBox      =   0   'False
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   MaxButton       =   0   'False
   MinButton       =   0   'False
   ScaleHeight     =   3135
   ScaleWidth      =   4650
   StartUpPosition =   1  'CenterOwner
   Begin VB.CommandButton cmdOK 
      Caption         =   "OK"
      Height          =   495
      Left            =   120
      TabIndex        =   2
      Top             =   2520
      Width           =   1215
   End
   Begin VB.CommandButton cmdCancel 
      Cancel          =   -1  'True
      Caption         =   "Cancel"
      Height          =   495
      Left            =   3300
      TabIndex        =   1
      Top             =   2520
      Width           =   1215
   End
   Begin MSComctlLib.ListView lvw 
      Height          =   2175
      Left            =   120
      TabIndex        =   0
      Top             =   120
      Width           =   4395
      _ExtentX        =   7752
      _ExtentY        =   3836
      View            =   3
      LabelEdit       =   1
      Sorted          =   -1  'True
      LabelWrap       =   -1  'True
      HideSelection   =   -1  'True
      FullRowSelect   =   -1  'True
      _Version        =   393217
      ForeColor       =   -2147483640
      BackColor       =   -2147483643
      BorderStyle     =   1
      Appearance      =   1
      NumItems        =   1
      BeginProperty ColumnHeader(1) {BDD1F052-858B-11D1-B16A-00C0F0283628} 
         Key             =   "TemplateName"
         Text            =   "Process Template"
         Object.Width           =   2540
      EndProperty
   End
End
Attribute VB_Name = "frmProcessTemplate"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private mfCancel As Boolean

Private Sub cmdOK_Click()
    If lvw.SelectedItem Is Nothing Then Exit Sub
    mfCancel = False
    Me.Hide
End Sub

Public Function ShowChoose(oTemplates As ProcessTemplates, ByRef oProcessTemplate As ProcessTemplate) As Boolean
    Dim oPT As ProcessTemplate
    Dim li As ListItem
    For Each oPT In oTemplates
        Set li = lvw.ListItems.Add(, , oPT.Name)
    Next
    Me.Show vbModal
    If mfCancel Then
        ShowChoose = False
        Exit Function
    End If
    Set oProcessTemplate = oTemplates(lvw.SelectedItem.Text)
    ShowChoose = True
End Function

Private Sub cmdCancel_Click()
    mfCancel = True
    Me.Hide
End Sub
