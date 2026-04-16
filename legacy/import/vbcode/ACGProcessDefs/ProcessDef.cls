VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "ProcessDef"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
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

Private WithEvents mContainer As Container
Attribute mContainer.VB_VarHelpID = -1
Private mRoutings As Routings
Private mTasks As Tasks
Public GUID As String
Private mPropertyGroup As PropertyGroup
Public IsValid As Boolean
Public FirstTask As TaskDef
Public ProcessTemplate As String

Private Sub Class_Initialize()
    Set mContainer = New Container
    Set mTasks = New Tasks
    Set mTasks.ParentContainer = mContainer
    Set mRoutings = New Routings
    Set mRoutings.ParentContainer = mContainer
    Set mPropertyGroup = New PropertyGroup
    Dim oProps As Properties
    Set oProps = mPropertyGroup.Add(cSysPropGroup)
    With oProps
        .Add "Name", vbNullString, ptString, True
        .Add "Class Construct", vbNullString, ptString, False
        .Add "Class Destruct", vbNullString, ptString, False
    End With
End Sub

Private Sub mContainer_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub

Public Property Get Routings() As Routings
    Set Routings = mRoutings
End Property

Public Property Get Tasks() As Tasks
    Set Tasks = mTasks
End Property

Public Property Get Name() As String
    Name = mPropertyGroup.Item(cSysPropGroup).Item(cPropName).Value
End Property

Public Property Let Name(v As String)
    mPropertyGroup.Item(cSysPropGroup).Item(cPropName).Value = v
End Property

Public Property Get PropertyGroup() As PropertyGroup
    Set PropertyGroup = mPropertyGroup
End Property
